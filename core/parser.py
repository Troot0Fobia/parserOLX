import re
import textwrap
import time
from collections.abc import Callable
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup as BS
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from textual.app import App

from core.paths import get_chrome_profiles_path
from core.state_manager import ParserState, load_state, save_state
from helpers.humanization import Humanization, ViewportSize

BASE_URL = "https://www.olx.ua"

BTN_SHOW_PHONE = 'button[data-testid="show-phone"].css-1mems40'
PHONE_VALUE = 'a[data-testid="contact-phone"]'
USER_NAME = '[data-testid="user-profile-user-name"]'
USER_PROFILE_LINK = 'a[data-testid="user-profile-link"][name="user_ads"]'

MAP_ASIDE = 'div[data-testid="map-aside-section"]'
MAP_CITY = ".css-9pna1a"
MAP_REGION = ".css-3cz5o2"

NEXT_IMAGE_BUTTON = "button.swiper-button-next"
PREV_IMAGE_BUTTON = "button.swiper-button-prev"

AUTH_CHECK = '[data-testid="qa-user-dropdown"]'
CAPTCHA_ROOT = 'iframe[title="reCAPTCHA"], div[id*="captcha"], [data-testid*="captcha"]'
SPAM_ALERT = 'p[class="css-rdovvl"][role="alert"]'

BS_CARD_CLASS = "css-1sw7q4x"
BS_CARD_DATASET = "l-card"
BS_CARD_LINK_CLASS = "css-1tqlkj0"
BS_PAGE_WRAPPER_DATASET = "pagination-list"
BS_PAGE_WRAPPER_CLASS = "pagination-list"
BS_PAGE_LINK_CLASS = "css-b6tdh7"

DEFAULT_TIMEOUT = 10


class Parser:

    def __init__(
        self,
        app: App,
        log_output: Callable[[str, int], None],
        add_data: Callable[[dict], None],
    ):
        self.main_app = app
        self.log_output = log_output
        self.add_data = add_data
        self._running = False
        self.state = ParserState()
        self.profile = None
        self.processed_cards = 0
        self.driver = webdriver.Chrome()
        self.humanization = Humanization()
        self.viewport_size = ViewportSize()

        self.options = Options()
        self.options.add_argument("--disable-blink-features=AutomationControlled")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")

        profiles_path = get_chrome_profiles_path()
        if not profiles_path:
            raise ValueError("Не удалось получить путь к профилям")

        self.options.add_argument(f"--user-data-dir={profiles_path}")

    def start(
        self,
        url: str,
        proceed: bool = False,
    ) -> None:
        if proceed:
            self.state = load_state()
            if not self.state.url or not self.state.cards:
                return
        elif url:
            self.state.url = url
            self.receive_cards()
        else:
            self.log_output("Неизвестное состояние.", 0)
            return

        self.profiles = self.main_app.getSetting("profiles").copy()
        if not self.profiles:
            self.log_output("Нет активных профилей.", 0)
            return

        self.log_output(f"Активные профили: {self.profiles}", 1)

        self._running = True
        while self._running and len(self.state.cards):
            card_link = self.state.cards.pop()
            try:
                if not self.profile and not self.change_profile():
                    raise ValueError(
                        f"Current profile {self.profile} does not authorized. Switching..."
                    )

                self.driver.get(card_link)
                next_button, prev_button = self.get_image_buttons()
                if next_button and prev_button:
                    self.humanization.scroll_images(
                        next_button=next_button, prev_button=prev_button
                    )

                phone_button = self.find_show_phone()
                if phone_button is None:
                    continue

                time.sleep(2)

                if self.viewport_size.width and self.viewport_size.height:
                    self.humanization.human_imitation(
                        self.driver,
                        show_phone_button=phone_button,
                        viewport_size=self.viewport_size,
                    )

                try:
                    phone_button.click()
                except Exception:
                    continue
                time.sleep(3)

                if self.is_captcha():
                    raise ValueError("Profile catched captcha. Switching...")

                if self.is_spam():
                    raise ValueError("Profile catched spam block. Switching...")

                phone = self.get_phone()
                user_name = self.get_user_name()
                profile_link = self.get_user_profile_link()
                city, region = self.get_location()
                self.log_output(
                    (
                        f"Получены данные продавца: Номер телефона: [cyan]{phone}[/cyan],"
                        f"Имя продавца: [cyan]{user_name}[/cyan],"
                        f"Ссылка профиля: [cyan]{profile_link}[/cyan],"
                        f"Местоположение: [cyan]{city}, {region}[/cyan]"
                    ),
                    1,
                )
                self.add_data(
                    {
                        "username": user_name,
                        "phone": phone,
                        "profile_link": profile_link,
                        "city": city,
                        "region": region,
                    }
                )
            except ValueError as e:
                self.log_output(
                    (
                        "Возникла ошибка с аккаунтом во время парсинга:\n"
                        + textwrap.indent(str(e) or repr(e), " " * 9)
                    ),
                    0,
                )
                self.state.cards.append(card_link)
                self.processed_cards -= 1
                self.profile = None
            except Exception as e:
                self.log_output(
                    (
                        "Возникла ошибка во время парсинга:\n"
                        + textwrap.indent(str(e) or repr(e), " " * 9)
                    ),
                    0,
                )
                self.state.cards.append(card_link)
                self.processed_cards -= 1
            finally:
                self.processed_cards += 1

        save_state(self.state)

    def change_profile(self) -> bool:
        self.stop()
        if not self.profiles:
            self.wait_time()

        self.profile = self.profiles.pop()

        self.options.add_argument(f"--profile-directory={self.profile}")
        self.driver = webdriver.Chrome(options=self.options)
        self.driver.get(self.state.url)
        self.driver.maximize_window()
        self.get_user_viewport_size()

        if not self.is_auth():
            self.profile = None
            return False

        return True

    def wait_time(self) -> None:
        wait_count = 30 * 60
        self.log_output(
            f"Профили закончились, ожидаем {wait_count / 60} минут для повтора...", 1
        )
        time.sleep(wait_count)
        self.profiles = self.main_app.getSetting("profiles").copy()

    def get_user_viewport_size(self) -> None:
        height = self.driver.execute_script(
            "return document.documentElement.clientHeight;"
        )
        width = self.driver.execute_script(
            "return document.documentElement.clientWidth;"
        )

        if height and width:
            self.viewport_size = ViewportSize(width, height)

    def refresh_options(self) -> None:
        args = [
            arg
            for arg in self.options.arguments
            if not arg.startswith("--profile-directory")
        ]
        self.options.arguments.clear()
        for arg in args:
            self.options.add_argument(arg)

    def get_image_buttons(self) -> tuple[WebElement, WebElement] | tuple[None, None]:
        try:
            next_button = self.driver.find_element(By.CSS_SELECTOR, NEXT_IMAGE_BUTTON)
            prev_button = self.driver.find_element(By.CSS_SELECTOR, PREV_IMAGE_BUTTON)
            return next_button, prev_button
        except Exception:
            pass

        return None, None

    def is_captcha(self) -> bool:
        try:
            self.driver.find_element(By.CSS_SELECTOR, CAPTCHA_ROOT)
            return True
        except Exception:
            pass

        return False

    def is_spam(self) -> bool:
        try:
            self.driver.find_element(By.CSS_SELECTOR, SPAM_ALERT)
            return True
        except Exception:
            pass

        return False

    def find_show_phone(self, timeout: float = DEFAULT_TIMEOUT) -> WebElement | None:
        try:
            if btn := WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, BTN_SHOW_PHONE))
            ):
                return btn
        except Exception:
            pass

        return None

    def get_phone(self, timeout: float = DEFAULT_TIMEOUT) -> str:
        phone = ""
        try:
            el = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, PHONE_VALUE))
            )
            if el and el.text.strip():
                phone = el.text.strip()

                phone = re.sub(r"\D", "", phone)
                phone = re.sub(r"^0", "", phone)
                if not phone.startswith("380"):
                    phone = "380" + phone
        except Exception:
            pass

        return phone

    def get_user_name(self) -> str:
        try:
            return self.driver.find_element(By.CSS_SELECTOR, USER_NAME).text.strip()
        except Exception:
            pass

        return ""

    def get_user_profile_link(self) -> str:
        try:
            el = self.driver.find_element(By.CSS_SELECTOR, USER_PROFILE_LINK)
            href = el.get_attribute("href")
            if href:
                return urljoin(BASE_URL, href)
        except Exception:
            pass

        return ""

    def get_location(self) -> tuple[str, str]:
        try:
            aside = self.driver.find_element(By.CSS_SELECTOR, MAP_ASIDE)
        except Exception:
            return "", ""
        city, region = "", ""
        try:
            city = (
                aside.find_element(By.CSS_SELECTOR, MAP_CITY)
                .text.strip()
                .replace(",", "")
            )
        except Exception:
            pass
        try:
            region = aside.find_element(By.CSS_SELECTOR, MAP_REGION).text.strip()
        except Exception:
            pass

        return city, region

    def is_auth(self) -> bool:
        try:
            self.driver.find_element(By.CSS_SELECTOR, AUTH_CHECK)
            return True
        except Exception:
            pass

        return False

    def stop(self) -> None:
        save_state(self.state)
        if self.driver:
            self.driver.quit()
        self.refresh_options()

    def close(self) -> None:
        if not self._running:
            return
        self._running = False
        self.stop()
        self.log_output("Парсер остановлен", 1)

    def increase_page(self, url: str) -> tuple[str, int]:
        obj = urlparse(url)
        query_params = parse_qs(obj.query)
        if query_params.get("page", None):
            query_params["page"] = [str(int(query_params["page"][0]) + 1)]
        else:
            query_params["page"] = ["2"]

        new_query = urlencode(query_params, doseq=True)

        return str(urlunparse(obj._replace(query=new_query))), int(
            query_params["page"][0]
        )

    def extract_url_parts(self, url: str) -> tuple[str, str, int]:
        obj = urlparse(url)
        query_params = parse_qs(obj.query)
        page = 1
        if query_params.get("page", None):
            page = int(query_params["page"][0])
        return obj.scheme, obj.netloc, page

    def get_max_page_number(self, soup: BS) -> int:
        try:
            page_wrapper = soup.find(
                "ul",
                attrs={
                    "class": BS_PAGE_WRAPPER_CLASS,
                    "data-testid": BS_PAGE_WRAPPER_DATASET,
                },
            )
            if not page_wrapper:
                return 1

            page_links = page_wrapper.find_all("a", attrs={"class": BS_PAGE_LINK_CLASS})

            if not page_links:
                return 1

            max_page = 1
            for page_link in page_links:
                page_number = page_link.text.strip()
                if page_number.isdigit() and int(page_number) > max_page:
                    max_page = int(page_number)

            return max_page
        except Exception:
            pass

        return 1

    def receive_cards(self) -> None:
        self.log_output("Получаем карточки...", 1)
        cards = set()
        schema, netloc, current_page = self.extract_url_parts(self.state.url)
        max_page = -1

        while True:
            if max_page != -1 and current_page > max_page:
                break
            response = requests.get(self.state.url)

            if not response.ok:
                self.state.url, current_page = self.increase_page(self.state.url)
                continue

            soup = BS(response.content, "html.parser")
            cards_list = soup.find_all(
                "div",
                attrs={
                    "data-cy": BS_CARD_DATASET,
                    "data-testid": BS_CARD_DATASET,
                    "class": BS_CARD_CLASS,
                },
            )

            for card in cards_list:
                link_tag = card.find("a", class_=BS_CARD_LINK_CLASS)
                if link_tag and link_tag.has_attr("href"):
                    href = link_tag.get("href", "")
                    if href:
                        cards.add(urljoin(f"{schema}://{netloc}", str(href)))

            if max_page == -1:
                max_page = self.get_max_page_number(soup)
                self.log_output(f"Всего страниц: {max_page}", 1)

            self.log_output(f"Текущая страница: {current_page}", 1)
            self.state.url, current_page = self.increase_page(self.state.url)

        self.state.cards = list(cards)
        save_state(self.state)
        self.log_output(f"Получено {len(self.state.cards)} карточек.", 1)

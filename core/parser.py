import json
import platform
import random
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import pyautogui
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from core.paths import ROOT_DIR

BASE_URL = "https://www.olx.ua"
LISTING_GRID = '[data-testid="listing-grid"]'
CARD_SEL = 'div[data-cy="l-card"][data-testid="l-card"]'
CARD_PROMO_SKIP_INNER = ".css-175vbgm"
BTN_SHOW_PHONE = 'button[data-testid="show-phone"].css-1mems40'
PHONE_VALUE = 'a[data-testid="contact-phone"]'
USER_NAME = '[data-testid="user-profile-user-name"]'
USER_PROFILE_LINK = 'a[data-testid="user-profile-link"][name="user_ads"]'
MAP_ASIDE = 'div[data-testid="map-aside-section"]'
MAP_CITY = ".css-7wnksb"
MAP_REGION = ".css-z0m36u"
PAGINATION_WRAPPER = 'div[data-testid="pagination-wrapper"][data-cy="pagination"]'
PAGINATION_ITEMS = 'li[data-testid="pagination-list-item"]'

AUTH_CHECK = '[data-testid="qa-user-dropdown"]'
CAPTCHA_ROOT = 'iframe[title="reCAPTCHA"], div[id*="captcha"], [data-testid*="captcha"]'
SPAM_ALERT = 'p[class="css-rdovvl"][role="alert"]'

PAGINATION_NEXT = 'a[data-testid="pagination-forward"][data-cy="pagination-forward"]'

DEFAULT_TIMEOUT = 10


@dataclass
class ParserState:
    url: str = ""
    page_number: int = 1
    card_index: int = 0


class Parser:

    def __init__(self, app):
        self.main_app = app
        self._running = False
        self.options = Options()
        self.state = ParserState()
        self.options.add_argument("--disable-blink-features=AutomationControlled")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        profiles_path = ""
        if platform.system() == "Linux":
            profiles_path = Path.home() / ".config" / "chromium"
        else:
            profiles_path = (
                Path("C:/") / "1" / "GoogleChromePortable" / "Data" / "profile"
            )
        self.options.add_argument(f"--user-data-dir={profiles_path}")

    def start(
        self, url, log_output: callable, add_data: callable, proceed: bool = False
    ):
        if not proceed or self.state.url is not None:
            self.state.url = url
        else:
            self.load_state()
        self.add_data = add_data
        self.log_output = log_output
        self.profiles = self.main_app.getSetting("profiles").copy()
        self.log_output(f"Активные профили: {self.profiles}", 1)
        self._running = True

        while self._running:
            profile = None
            if len(self.profiles):
                profile = self.profiles.pop()
            if profile is None:
                self.stop()
                self.wait_time()
                continue
                # self._running = False
                # break

            self.options.add_argument(f"--profile-directory={profile}")
            self.driver = webdriver.Chrome(options=self.options)
            # if self.state.page_number != 1:
            self.fix_url()
            self.log_output(f"Url before receiving content: {self.state.url}")
            self.driver.get(self.state.url)
            self.driver.maximize_window()

            if not self.is_auth():
                self.log_output(f"Текущий профиль {profile} не авторизован", 0)
                print(f"Current profile [magenta]{profile}[/magenta] is not authorized")
                self.stop()
                continue

            while True:
                self.total_pages = self.get_total_pages()

                if self.state.page_number > self.total_pages:
                    self._running = False
                    self.stop()
                    break

                self.next_page_button = self.get_next_page_button()

                listing_grid = self.get_listing_grid()
                if listing_grid is None:
                    self.close()
                    break

                cards = self.get_cards(listing_grid)
                try:
                    self.process_cards(cards)
                except ValueError as e:
                    self.log_output(f"Пойман спам блок для профиля: {profile}: {e}", 0)
                    self.stop()
                    break

                if self.next_page_button is None:
                    self._running = False
                    self.stop()
                    break

                self.state.page_number += 1
                self.state.card_index = 0
                self.save_state()
                self.next_page_button.click()
                time.sleep(5)

    def process_cards(self, cards):
        start_idx = self.state.card_index
        for idx, card in enumerate(cards):
            try:
                if idx < start_idx:
                    continue

                if self.is_promo_card(card):
                    continue

                if (
                    card.get_attribute("data-cy") != "l-card"
                    or card.get_attribute("data-testid") != "l-card"
                ):
                    continue

                link = None
                try:
                    link_el = card.find_element(By.TAG_NAME, "a")
                    link = link_el.get_attribute("href")
                except Exception:
                    continue

                if not link:
                    continue

                try:
                    self.open_in_new_tab(link)
                except ValueError as e:
                    raise e

                try:
                    phone_button = self.find_show_phone()
                    if phone_button is None:
                        continue

                    time.sleep(2)
                    try:
                        phone_button.click()
                    except Exception:
                        continue
                    time.sleep(3)

                    if self.is_captcha():
                        raise ValueError("Profile catched captcha. Switching...")

                    is_spam = self.is_spam()
                    if is_spam is None:
                        self.driver.execute_script("window.scrollBy(0, 300);")
                        button_location = phone_button.location
                        button_size = phone_button.size

                        center_x = button_location["x"] + button_size["width"] / 2
                        center_y = button_location["y"] + button_size["height"] / 2

                        window_position = self.driver.get_window_position()
                        window_x, window_y = window_position["x"], window_position["y"]

                        absolute_x = window_x + center_x + random.uniform(0.3, 4.7)
                        absolute_y = window_y + center_y + random.uniform(0.3, 4.7) + 85

                        pyautogui.moveTo(
                            absolute_x, absolute_y, duration=random.uniform(0.3, 0.7)
                        )
                        time.sleep(1)
                        pyautogui.click()
                        time.sleep(1)
                    elif is_spam:
                        raise ValueError("Profile catched spam block. Switching...")

                    phone: str = self.get_phone()
                    if phone:
                        phone = re.sub(r"\D", "", phone)
                        phone = re.sub(r"^0", "", phone)
                        if not phone.startswith("380"):
                            phone = "380" + phone
                    user_name = self.get_user_name()
                    profile_link = self.get_user_profile_link()
                    city, region = self.get_location()
                    self.log_output(
                        (
                            f"Получены данные продавца: Номер телефона: [cyan]{phone}[/cyan],"
                            f"Имя продавца: [cyan]{user_name}[/cyan],"
                            f"Ссылка профиля: [cyan]{profile_link}[/cyan],"
                            f"Местоположение: [cyan]{city}, {region}[/cyan]"
                        )
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
                finally:
                    self.close_current_tab()

                self.state.card_index += 1
                time.sleep(5)
            except ValueError as e:
                raise e
            except Exception as e:
                self.log_output(f"Возникла ошибка: {e}", 1)

    def is_promo_card(self, card) -> bool:
        try:
            card.find_element(By.CSS_SELECTOR, CARD_PROMO_SKIP_INNER)
            return True
        except Exception:
            pass

        return False

    def is_captcha(self):
        try:
            self.driver.find_element(By.CSS_SELECTOR, CAPTCHA_ROOT)
            return True
        except Exception:
            pass

        return False

    def is_spam(self):
        try:
            spam_alert = self.driver.find_element(By.CSS_SELECTOR, SPAM_ALERT)
            if "activity" in spam_alert:
                return None
            if spam_alert:
                return True
        except Exception:
            pass

        return False

    def open_in_new_tab(self, url: str):
        self.driver.execute_script("window.open(arguments[0], '_blank');", url)
        self.driver.switch_to.window(self.driver.window_handles[-1])

    def close_current_tab(self):
        self.driver.close()
        self.driver.switch_to.window(self.driver.window_handles[0])

    def find_show_phone(self, timeout=DEFAULT_TIMEOUT):
        try:
            btn = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, BTN_SHOW_PHONE))
            )
            if btn:
                return btn
        except Exception:
            pass

        return None

    def get_phone(self, timeout=DEFAULT_TIMEOUT):
        try:
            el = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, PHONE_VALUE))
            )
            return el.text.strip()
        except Exception:
            pass

        return ""

    def get_user_name(self):
        try:
            return self.driver.find_element(By.CSS_SELECTOR, USER_NAME).text.strip()
        except Exception:
            pass

        return None

    def get_user_profile_link(self):
        try:
            el = self.driver.find_element(By.CSS_SELECTOR, USER_PROFILE_LINK)
            href = el.get_attribute("href") or ""
            return urljoin(BASE_URL, href)
        except Exception:
            pass

        return None

    def get_location(self):
        try:
            aside = self.driver.find_element(By.CSS_SELECTOR, MAP_ASIDE)
        except Exception:
            return "", ""
        city, region = "", ""
        try:
            city = aside.find_element(By.CSS_SELECTOR, MAP_CITY).text
            if city:
                city = city.strip().rstrip(",")
        except Exception:
            pass
        try:
            region = aside.find_element(By.CSS_SELECTOR, MAP_REGION).text
            if region:
                region = region.strip()
        except Exception:
            pass

        return city, region

    def is_auth(self):
        try:
            wait = WebDriverWait(self.driver, 10)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, LISTING_GRID)))
            self.driver.find_element(By.CSS_SELECTOR, AUTH_CHECK)
            return True
        except Exception:
            pass

        return False

    def get_total_pages(self):
        try:
            wrapper = self.driver.find_element(By.CSS_SELECTOR, PAGINATION_WRAPPER)
            page_items = wrapper.find_elements(By.CSS_SELECTOR, PAGINATION_ITEMS)

            items = []
            for page_item in page_items:
                link = page_item.find_element(By.TAG_NAME, "a")
                text = link.text.strip()
                if text.isdigit():
                    items.append(int(text))
            return max(items)

        except Exception:
            pass

        return 1

    def get_next_page_button(self):
        try:
            wrapper = self.driver.find_element(By.CSS_SELECTOR, PAGINATION_WRAPPER)
            if wrapper:
                next_btn = wrapper.find_element(By.CSS_SELECTOR, PAGINATION_NEXT)
                return next_btn
        except Exception:
            pass

        return None

    def get_listing_grid(self):
        try:
            return self.driver.find_element(By.CSS_SELECTOR, LISTING_GRID)
        except Exception:
            pass

        return None

    def get_cards(self, grid):
        try:
            return self.driver.find_elements(By.CSS_SELECTOR, CARD_SEL)
        except Exception:
            pass

        return None

    def stop(self):
        if self.driver:
            self.driver.quit()
        args = [
            arg
            for arg in self.options.arguments
            if not arg.startswith("--profile-directory")
        ]
        self.options.arguments.clear()
        for arg in args:
            self.options.add_argument(arg)
        self.save_state()

    def close(self):
        if not self._running:
            return
        self._running = False
        if self.driver:
            self.driver.quit()
        self.options = Options()
        self.save_state()

    def load_state(self):
        if not (ROOT_DIR / "state.json").exists():
            self.state = ParserState()
        else:
            data = json.loads((ROOT_DIR / "state.json").read_text())
            self.state = ParserState(**data)

    def save_state(self):
        (ROOT_DIR / "state.json").write_text(json.dumps(asdict(self.state)))

    def wait_time(self):
        wait_count = 30 * 60
        self.log_output(
            f"Профили закончились, ожидаем {wait_count / 60} минут для повтора..."
        )
        time.sleep(wait_count)
        self.profiles = self.main_app.getSetting("profiles").copy()

    def fix_url(self):
        obj = urlparse(self.state.url)
        query_params = parse_qs(obj.query)
        if (
            query_params.get("page", None)
            and int(query_params["page"][0]) > self.state.page_number
        ):
            self.state.page_number = int(query_params["page"][0])
        else:
            query_params["page"] = [str(self.state.page_number)]
            new_query = urlencode(query_params, doseq=True)
            self.state.url = urlunparse(obj._replace(query=new_query))


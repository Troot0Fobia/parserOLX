from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
import time
from pathlib import Path
import platform

BASE_URL = 'https://www.olx.ua'
LISTING_GRID = '[data-testid="listing-grid"]'
CARD_SEL = 'div[data-cy="l-card"][data-testid="l-card"]'
CARD_PROMO_SKIP_INNER = '.css-175vbgm'
BTN_SHOW_PHONE = 'button[data-testid="show-phone"]'
PHONE_VALUE = 'a[data-testid="contact-phone"]'
USER_NAME = '[data-testid="user-profile-user-name"]'
USER_PROFILE_LINK = 'a[data-testid="user-profile-link"][name="user_ads"]'
MAP_ASIDE = 'div[data-testid="map-aside-section"]'
MAP_CITY = '.css-7wnksb'
MAP_REGION = '.css-z0m36u'
PAGINATION_WRAPPER = 'div[data-testid="pagination-wrapper"][data-cy="pagination"]'
PAGINATION_ITEMS = 'li[data-testid="pagination-list-item"]'

AUTH_CHECK = '[data-testid="qa-user-dropdown"]'
CAPTCHA_ROOT = 'iframe[title="reCAPTCHA"], div[id*="captcha"], [data-testid*="captcha"]'
SPAM_ALERT = 'p[class="css-rdovvl"][role="alert"]'
SPAM_MESSAGE = 'Неможливо продовжити, оскільки ми виявили підозрілу активність'

PAGINATION_NEXT = 'a[data-testid="pagination-forward"][data-cy="pagination-forward"]'

DEFAULT_TIMEOUT = 10

@dataclass
class ParserState:
    url: str = None
    page_number: int = 1
    card_index: int = 0


class Parser:
    def __init__(self, app):
        self.main_app = app
        self.state = ParserState()
        self._running = False
        self.options = Options()
        # self.options.add_argument("--headless=new")
        self.options.add_argument("--disable-blink-features=AutomationControlled")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        profiles_path = ''
        if platform.system() == "Linux":
            profiles_path = Path.home() / '.config' / 'chromium'
        else:
            profiles_path = Path('C:/') / '1' / 'GoogleChromePortable' / 'Data' / 'profile'
        self.options.add_argument(f"--user-data-dir={profiles_path}")


    def start(self, url, log_output: callable, add_data: callable):
        self.state.url = url
        self.add_data = add_data
        self.log_output = log_output
        self.profiles = self.main_app.getSetting('profiles').copy()
        self.log_output(f"Активные профили: {self.profiles}", 1)
        self._running = True

        while self._running:
            profile = None
            if len(self.profiles):
                profile = self.profiles.pop()
            if profile is None:
                self._running = False
                self.stop()
                break

            self.options.add_argument(f"--profile-directory={profile}")
            self.driver = webdriver.Chrome(options=self.options)
            if self.state.page_number != 1:
                self.fix_url()
            self.driver.get(self.state.url)

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
                    self.stop()
                    break

                cards = self.get_cards(listing_grid)
                try:
                    self.process_cards(cards)
                except ValueError as e:
                    self.log_output(f"Пойман спам блок для профиля: {profile}: {e}", 0)
                    print(f"Catched spam block for profile: {profile}: {e}")
                    self.stop()
                    break
                
                if self.next_page_button is None:
                    self._running = False
                    self.stop()
                    break

                self.next_page_button.click()
                self.state.page_number += 1
                self.state.card_index = 0
                time.sleep(5)


    def process_cards(self, cards):
        start_idx = self.state.card_index
        for idx, card in enumerate(cards):
            if idx < start_idx:
                continue
            
            if self.is_promo_card(card):
                continue

            if card.get_attribute('data-cy') != 'l-card' or card.get_attribute('data-testid') != 'l-card':
                continue

            link = None
            try:
                link_el = card.find_element(By.TAG_NAME, 'a')
                link = link_el.get_attribute('href')
            except Exception:
                continue

            if not link:
                continue
            
            try:
                self.open_in_new_tab(link)
            except ValueError as e:
                raise e

            try:
                self.click_show_phone()
                time.sleep(5)
                if self.is_captcha() or self.is_spam():
                    raise ValueError("Profile catched spam block. Switching...")
                phone = self.get_phone()
                phone = phone.lstrip('+')
                if not phone.startswith('380'):
                    phone = '380' + phone
                user_name = self.get_user_name()
                profile_link = self.get_user_profile_link()
                city, region = self.get_location()
                self.log_output(f"Получены данные продавца: Номер телефона: [cyan]{phone}[/cyan], Имя продавца: [cyan]{user_name}[/cyan], Ссылка профиля: [cyan]{profile_link}[/cyan], Местоположение: [cyan]{city}, {region}[/cyan]")
                print(f"""
                    Получены данные продавца: Номер телефона: {phone}, Имя продавца: {user_name}, Ссылка профиля: {profile_link}, Местоположение: {city}, {region}
                """)
                self.add_data({
                    "username": user_name,
                    "phone": phone,
                    "profile_link": profile_link,
                    "city": city,
                    "region": region
                })
            finally:
                self.close_current_tab()

            self.state.card_index += 1
            time.sleep(5)


    def is_promo_card(self, card) -> bool:
        try:
            card.find_element(By.CSS_SELECTOR, CARD_PROMO_SKIP_INNER)
            return True
        except:
            return False

    def is_captcha(self):
        try:
            self.driver.find_element(By.CSS_SELECTOR, CAPTCHA_ROOT)
            return True
        except Exception:
            return False


    def is_spam(self):
        try:
            spam_alert = self.driver.find_element(By.CSS_SELECTOR, SPAM_ALERT)
            if spam_alert and SPAM_MESSAGE in spam_alert.text:
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


    def click_show_phone(self, timeout=DEFAULT_TIMEOUT):
        try:
            btn = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, BTN_SHOW_PHONE))
            )
            btn.click()
            return True
        except Exception:
            return False


    def get_phone(self, timeout=DEFAULT_TIMEOUT):
        try:
            el = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, PHONE_VALUE))
            )
            return el.text.strip()
        except Exception:
            return None


    def get_user_name(self):
        try:
            return self.driver.find_element(By.CSS_SELECTOR, USER_NAME).text.strip()
        except Exception:
            return None


    def get_user_profile_link(self):
        try:
            el = self.driver.find_element(By.CSS_SELECTOR, USER_PROFILE_LINK)
            href = el.get_attribute("href") or ""
            return urljoin(BASE_URL, href)
        except Exception:
            return None


    def get_location(self):
        try:
            aside = self.driver.find_element(By.CSS_SELECTOR, MAP_ASIDE)
        except Exception:
            return None
        city, region = None, None
        try:
            city = aside.find_element(By.CSS_SELECTOR, MAP_CITY).text.strip().rstrip(',')
        except Exception:
            pass
        try:
            region = aside.find_element(By.CSS_SELECTOR, MAP_REGION).text.strip()
        except Exception:
            pass
        return city, region


    def is_auth(self):
        try:
            wait = WebDriverWait(self.driver, 10)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, LISTING_GRID)))
            self.driver.find_element(By.CSS_SELECTOR, AUTH_CHECK)
            return True
        except:
            return False


    def get_total_pages(self):
        try:
            wrapper = self.driver.find_element(By.CSS_SELECTOR, PAGINATION_WRAPPER)
            page_items = wrapper.find_elements(By.CSS_SELECTOR, PAGINATION_ITEMS)
            
            items = []
            for page_item in page_items:
                link = page_item.find_element(By.TAG_NAME, 'a')
                text = link.text.strip()
                if text.isdigit():
                    items.append(int(text))
            return max(items)

        except:
            return 1


    def get_next_page_button(self):
        try:
            wrapper = self.driver.find_element(By.CSS_SELECTOR, PAGINATION_WRAPPER)
            next_btn = wrapper.find_element(By.CSS_SELECTOR, PAGINATION_NEXT)
            return next_btn
        except:
            return None


    def get_listing_grid(self):
        try:
            return self.driver.find_element(By.CSS_SELECTOR, LISTING_GRID)
        except:
            return None


    def get_cards(self, grid):
        try:
            return self.driver.find_elements(By.CSS_SELECTOR, CARD_SEL)
        except:
            return None


    def stop(self):
        if self.driver:
            self.driver.quit()
        args = [arg for arg in self.options.arguments if not arg.startswith('--profile-directory')]
        self.options.arguments.clear()
        for arg in args:
            self.options.add_argument(arg)


    def close(self):
        if not self._running:
            return
        self._running = False
        if self.driver:
            self.driver.quit()
        self.options = Options()


    def fix_url(self):
        obj = urlparse(self.state.url)
        query_params = parse_qs(obj.query)
        query_params['page'] = [str(self.state.page_number)]
        new_query = urlencode(query_params, doseq=True)
        self.state.url = urlunparse(obj._replace(query=new_query))

import random
import time
from dataclasses import dataclass

from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

SWIPER_DISABLED = "swiper-button-disabled"


@dataclass
class ViewportSize:
    width: int = 0
    height: int = 0


class Humanization:

    def scroll_images(self, next_button: WebElement, prev_button: WebElement):
        def buttonDisabled(button: WebElement) -> bool:
            if class_name := button.get_attribute("class"):
                return SWIPER_DISABLED in class_name
            return False

        while True:
            if random.uniform(0, 1) < 0.85:
                if not buttonDisabled(next_button):
                    next_button.click()
                else:
                    break
            else:
                if not buttonDisabled(prev_button):
                    prev_button.click()

            time.sleep(random.uniform(0.7, 1.3))

    def human_imitation(
        self,
        driver: WebDriver,
        show_phone_button: WebElement,
        viewport_size: ViewportSize,
    ):
        viewport_height_center = viewport_size.height // 2
        optimal_viewport_height = viewport_size.height * random.uniform(0.3, 0.65)
        optimal_viewport_center = optimal_viewport_height // 2
        center_offset = viewport_height_center - optimal_viewport_center

        top_bound_pos = center_offset
        bottom_bound_pos = optimal_viewport_height + center_offset

        current_position = 0
        button_y_coord = show_phone_button.location["y"]
        while True:
            if button_y_coord < bottom_bound_pos and button_y_coord >= top_bound_pos:
                break

            if button_y_coord > bottom_bound_pos:
                current_position += random.randint(60, 150)
            elif button_y_coord < top_bound_pos:
                current_position -= random.randint(50, 100)

            driver.execute_script(f"window.scrollTo(0, {current_position})")
            time.sleep(random.uniform(0.13, 0.34))
            button_y_coord = driver.execute_script(
                "return arguments[0].getBoundingClientRect().y;", show_phone_button
            )

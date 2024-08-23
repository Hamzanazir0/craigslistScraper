import sys
import os
import requests
import gspread
import threading
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QCheckBox,
)
from PySide6.QtCore import Qt, QThread, Signal
from oauth2client.service_account import ServiceAccountCredentials
from scrapy.selector import Selector
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urlparse, urlunparse


class CraigslistScraper(QThread):
    log_signal = Signal(str)

    def __init__(
        self, sheet_name, credentials_file, location, keyword_input, category_input
    ):
        super().__init__()
        # self.sheet_name = sheet_name
        # self.credentials_file = credentials_file
        self.location = location
        self.keyword_input = keyword_input
        self.category_input = category_input
        self.country = "Canada"
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "DNT": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }
        # self.google_sheet = self.connect_to_google_sheet()
        self.scraping = False
        self.driver = None
        self.stop_event = threading.Event()

    def log(self, message):
        self.log_signal.emit(message)

    # def connect_to_google_sheet(self):
    #     scope = [
    #         "https://spreadsheets.google.com/feeds",
    #         "https://www.googleapis.com/auth/spreadsheets",
    #         "https://www.googleapis.com/auth/drive.file",
    #         "https://www.googleapis.com/auth/drive",
    #     ]
    #     creds = ServiceAccountCredentials.from_json_keyfile_name(
    #         self.credentials_file, scope
    #     )
    #     client = gspread.authorize(creds)
    #     sheet = client.open(self.sheet_name).sheet1

    #     if not sheet.row_values(1):
    #         headers = [
    #             "Country",
    #             "City",
    #             "Category",
    #             "Keyword",
    #             "Post Title",
    #             "Link",
    #             "Date",
    #         ]
    #         sheet.insert_row(headers, 1)

    #     return sheet

    def fetch_url(self, url, retries=3):
        for attempt in range(retries):
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                return response
            else:
                self.log(
                    f"[Retry {attempt + 1}/{retries}] Failed to fetch {url} - Status Code: {response.status_code}"
                )
        self.log(
            f"[Error] Failed to get a successful response after {retries} attempts for {url}"
        )
        return None

    def scrape(self, url):
        response = self.fetch_url(url)
        if not response:
            return

        self.country = "Canada" if "CA" in response.url else "US"
        resp = Selector(text=response.content)

        city_elements = resp.xpath(
            f"//h2[contains(text(),'{self.country}')]//following-sibling::div[1]//ul/li/a"
        )
        city_data = [
            (city.xpath("text()").get().strip(), city.xpath("@href").get())
            for city in city_elements
        ]
        self.log(f"[{self.country}] Found {len(city_data)} cities to scrape.")

        for index, (city_name, city_url) in enumerate(city_data, start=1):
            if self.stop_event.is_set():
                break
            self.log(
                f"[{self.country} | {city_name}] Scraping city {index}/{len(city_data)}: {city_url}"
            )
            response = self.fetch_url(city_url)
            if response:
                self.scrape_categories(response, city_url, city_name)

    def scrape_categories(self, response, city_url, city_name):
        resp = Selector(text=response.content)

        keyword = self.keyword_input.text()
        category = self.category_input.text()

        self.log(f"[{self.country} | {city_name}] Scraping Category: {category}")

        category_page_url_unfiltered = self.get_category_page_url(
            resp, category, city_url, city_name
        )
        if category_page_url_unfiltered:
            category_page_url = self.update_category_url(category_page_url_unfiltered)
            if category_page_url:
                self.log(
                    f"[{self.country} | {city_name}] Found Category URL: {category_page_url}"
                )
                self.scrape_posts_selenium(
                    category, keyword, category_page_url, city_url, city_name
                )
        else:
            self.log(
                f"[{self.country} | {city_name}] Skipping category '{category}' due to missing page."
            )

    def get_category_page_url(self, resp, category, base_url, city_name):
        category_xpath = f"//a[contains(@data-alltitle,'{category}')]/@href"
        category_page_url = resp.xpath(category_xpath).extract_first()

        if not category_page_url or "#" in category_page_url:
            category_page_url = resp.xpath(
                f"//a[contains(@data-alltitle,'{category.lower()}')]/@href"
            ).extract_first()

        if category_page_url and not category_page_url.startswith(("http:", "https:")):
            category_page_url = (
                base_url.rstrip("/") + "/" + category_page_url.lstrip("/")
            )

        if not category_page_url:
            self.log(
                f"[{self.country} | {city_name}] Category page not found for '{category}'. Moving on to the next category..."
            )
            return False

        return category_page_url

    def update_category_url(self, url):
        parsed_url = urlparse(url)
        fragment = parsed_url.fragment
        new_search_query = "1~thumb~0~0"

        if "#search" in url:
            fragment_parts = fragment.split("=", 1)
            if len(fragment_parts) > 1:
                if "thumb" not in fragment_parts[1]:
                    updated_fragment = f"search={new_search_query}"
                else:
                    updated_fragment = fragment
            else:
                updated_fragment = f"search={new_search_query}"
        else:
            updated_fragment = f"search={new_search_query}"

        updated_url = urlunparse(
            (
                parsed_url.scheme,
                parsed_url.netloc,
                parsed_url.path,
                parsed_url.params,
                parsed_url.query,
                updated_fragment,
            )
        )
        return updated_url

    def scrape_posts_selenium(
        self, category, keyword, category_page_url, city_url, city_name
    ):
        self.driver = webdriver.Chrome()
        self.driver.get(category_page_url)
        page_num = 0

        try:
            while not self.stop_event.is_set():
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "li.cl-search-result")
                    )
                )
                post_elements = self.driver.find_elements(
                    By.CSS_SELECTOR, "li.cl-search-result"
                )

                num_results = len(post_elements)
                self.log(
                    f"[{self.country} | {city_name}] Page {page_num + 1}: Found {num_results} posts in '{category}' looking for '{keyword}'."
                )

                if post_elements:
                    self.process_posts(
                        category, keyword, post_elements, city_url, city_name
                    )
                else:
                    self.log(
                        f"[{self.country} | {city_name}] No posts found for '{keyword}' in '{category}' on page {page_num + 1}."
                    )

                paginator = self.driver.find_element(
                    By.CSS_SELECTOR, "div.cl-search-paginator"
                )
                next_button = paginator.find_element(
                    By.CSS_SELECTOR, "button.bd-button.cl-next-page"
                )

                if "bd-disabled" in next_button.get_attribute("class"):
                    self.log(
                        f"[{self.country} | {city_name}] Reached last page in '{category}' for '{keyword}'. Moving to next city..."
                    )
                    break

                next_button.click()
                page_num += 1
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "li.cl-search-result")
                    )
                )

        except Exception as e:
            self.log(
                f"[{self.country} | {city_name}] Error occurred while scraping the category page: {e}"
            )

        finally:
            if self.driver:
                self.driver.quit()

    def process_posts(self, category, keyword, post_elements, city_url, city_name):
        existing_posts = self.get_existing_posts()

        for element in post_elements:
            if self.stop_event.is_set():
                break
            try:
                try:
                    title_element = element.find_element(
                        By.CSS_SELECTOR, "div.result-node a.posting-title span.label"
                    )
                    title = title_element.text.strip()
                except Exception as e:
                    self.log(f"[{self.country} | {city_name}] Title not found: {e}")
                    continue

                try:
                    url_element = element.find_element(
                        By.CSS_SELECTOR, "div.result-node a.posting-title"
                    )
                    url = url_element.get_attribute("href")
                except Exception as e:
                    self.log(f"[{self.country} | {city_name}] URL not found: {e}")
                    continue

                try:
                    date_element = element.find_element(
                        By.CSS_SELECTOR, "div.result-node div.meta span[title]"
                    )
                    date = date_element.get_attribute("title")
                except Exception as e:
                    self.log(f"[{self.country} | {city_name}] Date not found: {e}")
                    continue

                if keyword.lower() in title.lower():
                    key = f"{title}-{url}"
                    if key not in existing_posts:
                        self.log(
                            f"[{self.country} | {city_name}] Found matching post: {title}"
                        )
                        self.save_to_google_sheet(
                            [
                                self.country,
                                city_name,
                                category,
                                keyword,
                                title,
                                url,
                                date,
                            ]
                        )
                        existing_posts.add(key)
            except Exception as e:
                self.log(f"[{self.country} | {city_name}] Error processing post: {e}")

    def get_existing_posts(self):
        existing_posts = set()
        all_posts = self.google_sheet.get_all_values()
        for row in all_posts:
            key = f"{row[5]}-{row[6]}"
            existing_posts.add(key)
        return existing_posts

    def save_to_google_sheet(self, data):
        try:
            self.google_sheet.append_row(data)
            self.log(f"[{self.country}] Successfully saved post to Google Sheet.")
        except Exception as e:
            self.log(f"[{self.country}] Error saving post to Google Sheet: {e}")

    def run(self):
        self.scraping = True
        try:
            if self.location == "Canada":
                self.scrape("https://www.craigslist.org/about/sites#CA")
            elif self.location == "US":
                self.scrape("https://www.craigslist.org/about/sites#USA")
            elif self.location == "Both":
                self.scrape("https://www.craigslist.org/about/sites#CA")
                self.scrape("https://www.craigslist.org/about/sites#USA")
        finally:
            self.scraping = False

    def stop(self):
        self.scraping = False
        self.stop_event.set()
        if self.driver:
            self.driver.quit()


#
# Google Sheet Class and Methods
class GoogleSheetController:
    def __init__(self, sheet_name, sheet_page_name, credentials_file):
        self.sheet_name = sheet_name
        self.sheet_page_name = sheet_page_name
        self.credentials_file = credentials_file
        self.google_sheet = self.connect_to_google_sheet()

    def connect_to_google_sheet(self):
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            self.credentials_file, scope
        )
        client = gspread.authorize(creds)
        sheet = client.open(self.sheet_name).worksheet(self.sheet_page_name)

        if not sheet.row_values(1):
            headers = [
                "Country",
                "City",
                "Category",
                "Keyword",
                "Post Title",
                "Link",
                "Date",
            ]
            sheet.insert_row(headers, 1)

        return sheet

    def connect_to_google_sheet(self):
        try:
            # Define the scope for Google Sheets and Google Drive API
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive.file",
                "https://www.googleapis.com/auth/drive",
            ]

            # Authenticate using the service account credentials file
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                self.credentials_file, scope
            )
            client = gspread.authorize(creds)

            # Open the Google Sheet by name and access the specified worksheet
            sheet = client.open(self.sheet_name).worksheet(self.sheet_page_name)

            # Check if the first row is empty; if so, insert headers
            if not sheet.row_values(1):
                headers = [
                    "Country",
                    "City",
                    "Category",
                    "Keyword",
                    "Post Title",
                    "Link",
                    "Date",
                ]
                sheet.insert_row(headers, 1)

            return sheet

        except gspread.exceptions.SpreadsheetNotFound:
            logging.error(
                "The Google Sheet with the name '%s' was not found.", self.sheet_name
            )
            return None

        except gspread.exceptions.WorksheetNotFound:
            logging.error(
                "The worksheet with the name '%s' was not found in the Google Sheet.",
                self.sheet_page_name,
            )
            return None

        except FileNotFoundError:
            logging.error(
                "The credentials file '%s' was not found.", self.credentials_file
            )
            return None

        except Exception as e:
            logging.error(
                "An error occurred while connecting to the Google Sheet: %s", str(e)
            )
            return None


class CraigslistScraperUI(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Craigslist Scraper")
        self.resize(600, 500)

        # Country Selection
        self.country_label = QLabel("Select Country:")
        self.location_dropdown = QComboBox(self)
        self.location_dropdown.addItem("Select Location")
        self.location_dropdown.addItem("Canada")
        self.location_dropdown.addItem("US")
        self.location_dropdown.addItem("Both")
        self.location_dropdown.currentIndexChanged.connect(self.on_country_change)

        # State/Province Selection
        self.state_label = QLabel("Select State/Province:")
        self.state_search_input = QLineEdit(self)
        self.state_search_input.setPlaceholderText("Search states/provinces...")
        self.state_list = QListWidget(self)
        self.state_list.setSelectionMode(QListWidget.MultiSelection)
        self.select_all_states_checkbox = QCheckBox("Select All States/Provinces", self)
        # self.select_all_states_checkbox.stateChanged.connect(
        #     self.toggle_select_all_states
        # )

        # City Selection
        self.city_label = QLabel("Select City:")
        self.city_search_input = QLineEdit(self)
        self.city_search_input.setPlaceholderText("Search cities...")
        self.city_list = QListWidget(self)
        self.city_list.setSelectionMode(QListWidget.MultiSelection)
        self.select_all_cities_checkbox = QCheckBox("Select All Cities", self)
        # self.select_all_cities_checkbox.stateChanged.connect(
        #     self.toggle_select_all_cities
        # )

        # Keyword and Category Inputs
        self.keyword_label = QLabel("Keyword:")
        self.keyword_input = QLineEdit(self)
        self.category_label = QLabel("Category:")
        self.category_input = QLineEdit(self)

        # Buttons
        self.start_button = QPushButton("Start Scraping", self)
        self.start_button.clicked.connect(self.on_start_button_click)
        self.stop_button = QPushButton("Stop Scraping", self)
        self.stop_button.clicked.connect(self.on_stop_button_click)
        self.stop_button.setEnabled(False)
        self.clear_console_button = QPushButton("Clear Console")
        self.clear_console_button.clicked.connect(self.on_clear_console_click)

        self.log_output = QTextEdit(self)
        self.log_output.setReadOnly(True)

        # Layout
        form_layout = QVBoxLayout()
        form_layout.addWidget(QLabel("Select Location:"))
        form_layout.addWidget(self.location_dropdown)

        keyword_input = QVBoxLayout()
        keyword_input.addWidget(self.keyword_label)
        keyword_input.addWidget(self.keyword_input)
        category_input = QVBoxLayout()
        category_input.addWidget(self.category_label)
        category_input.addWidget(self.category_input)
        input_group = QHBoxLayout()
        input_group.addLayout(keyword_input)
        input_group.addLayout(category_input)
        form_layout.addLayout(input_group)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)

        form_layout.addLayout(button_layout)
        form_layout.addWidget(self.clear_console_button)
        form_layout.addWidget(self.log_output)

        self.setLayout(form_layout)

        self.scraper_thread = None

    def on_country_change(self):
        selected_country = self.country_dropdown.currentText()
        self.load_states(selected_country)

    def load_states(self, country):
        self.state_list.clear()
        states = []
        if country == "US":
            states = ["California", "New York", "Texas", ...]  # Load US states
        elif country == "Canada":
            states = [
                "Ontario",
                "Quebec",
                "British Columbia",
                ...,
            ]  # Load Canada provinces
        elif country == "Both":
            states = [
                "California",
                "New York",
                "Texas",
                "Ontario",
                "Quebec",
                "British Columbia",
                ...,
            ]  # Load both
        for state in states:
            self.state_list.addItem(QListWidgetItem(state))

    def on_start_button_click(self):
        location = self.location_dropdown.currentText()
        if location == "Select Location":
            self.log_output.append("Please select a location.")
            return
        if not self.keyword_input.text():
            self.log_output.append("Please enter a keyword.")
            return
        if not self.category_input.text():
            self.log_output.append("Please select a category.")
            return
        if self.scraper_thread and self.scraper_thread.isRunning():
            return
        self.log_output.append("Starting...")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        credentials_file_Name = "HamzaCred.json"
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.scraper_thread = CraigslistScraper(
            sheet_name="Craigslist Scraper Results",
            credentials_file=os.path.join(current_dir, credentials_file_Name),
            location=self.location_dropdown.currentText(),
            keyword_input=self.keyword_input,
            category_input=self.category_input,
        )
        self.scraper_thread.log_signal.connect(self.update_log)
        self.scraper_thread.start()
        self.log_output.append("Scraping started...")

    def on_stop_button_click(self):
        if self.scraper_thread and self.scraper_thread.isRunning():
            self.scraper_thread.stop_event.set()
            self.scraper_thread.quit()
            self.scraper_thread.wait()
            self.scraper_thread = None
            self.log_output.append("Scraping stopped.")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def on_clear_console_click(self):
        self.log_output.clear()

    def update_log(self, message):
        self.log_output.append(message)


def main():
    app = QApplication(sys.argv)
    window = CraigslistScraperUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

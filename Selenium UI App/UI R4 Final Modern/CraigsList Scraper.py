import sys
import os
import requests
import gspread
import math
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
    QGridLayout,
)
from PySide6.QtCore import Qt, QThread, Signal
from oauth2client.service_account import ServiceAccountCredentials
from scrapy.selector import Selector
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from collections import namedtuple
from urllib.parse import urlparse, urlunparse


class CraigslistScraper(QThread):
    log_signal = Signal(str)
    finished_signal = Signal()

    def __init__(self, sheet_info):
        super().__init__()
        self.selected_country = None
        self.processing_country = None
        self.selected_canadian_states = None
        self.selected_us_states = None
        self.selected_canadian_cities = None
        self.selected_us_cities = None
        self.keyword = None
        self.category = None
        self.sheet_info = sheet_info
        self.google_sheet = None
        self.default_url = "https://www.craigslist.org/about/sites"
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
        self.default_response_fetched = False
        if not self.default_response_fetched:
            self.default_response = self.fetch_url(self.default_url)
        self.scraping = False
        self.driver = None
        self.stop_event = threading.Event()

    def log(self, message):
        self.log_signal.emit(message)

    def fetch_url(self, url, retries=3):
        for attempt in range(retries):
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                self.default_response_fetched = True
                return response
            else:
                self.log(
                    f"[Retry {attempt + 1}/{retries}] Failed to fetch {url} - Status Code: {response.status_code}"
                )
        self.log(
            f"[Error] Failed to get a successful response after {retries} attempts for {url}"
        )
        return None

    def scrape(self):
        selected_cities = self.selected_canadian_cities + self.selected_us_cities
        self.log(
            f"[{self.selected_country}] {len(selected_cities)} cities to scrape.\n"
        )

        if self.selected_country == "Canada":
            self.processing_country = self.selected_country
            for index, city in enumerate(self.selected_canadian_cities, start=1):
                city_name = city.text()
                city_url = city.data(Qt.UserRole)
                if self.stop_event.is_set():
                    break
                self.log(
                    f"\n[{self.selected_country} | {city_name}] Scraping city {index}/{len(self.selected_canadian_cities)}"
                )
                city_page_response = self.fetch_url(city_url)
                if city_page_response:
                    self.scrape_categories(city_page_response, city_url, city_name)
                else:
                    self.log(
                        f"Response not found for city {city_name} moving to next city..."
                    )
        if self.selected_country == "US":
            self.processing_country = self.selected_country
            for index, city in enumerate(self.selected_us_cities, start=1):
                city_name = city.text()
                city_url = city.data(Qt.UserRole)
                if self.stop_event.is_set():
                    break
                self.log(
                    f"\n[{self.selected_country} | {city_name}] Scraping city {index}/{len(self.selected_us_cities)}"
                )
                city_page_response = self.fetch_url(city_url)
                if city_page_response:
                    self.scrape_categories(city_page_response, city_url, city_name)
                else:
                    self.log(
                        f"Response not found for city {city_name} moving to next city..."
                    )
        if self.selected_country == "Canada & US":
            self.processing_country = "Canada"
            for index, city in enumerate(self.selected_canadian_cities, start=1):
                city_name = city.text()
                city_url = city.data(Qt.UserRole)
                if self.stop_event.is_set():
                    break
                self.log(
                    f"\n[{self.processing_country} | {city_name}] Scraping city {index}/{len(self.selected_canadian_cities)}"
                )
                city_page_response = self.fetch_url(city_url)
                if city_page_response:
                    self.scrape_categories(city_page_response, city_url, city_name)
                else:
                    self.log(
                        f"Response not found for city {city_name} moving to next city..."
                    )
            self.log(f"\nSelected cities from {self.processing_country} scrapped.\n")
            self.processing_country = "US"
            for index, city in enumerate(self.selected_us_cities, start=1):
                city_name = city.text()
                city_url = city.data(Qt.UserRole)
                if self.stop_event.is_set():
                    break
                self.log(
                    f"\n[{self.processing_country} | {city_name}] Scraping city {index}/{len(self.selected_us_cities)}"
                )
                city_page_response = self.fetch_url(city_url)
                if city_page_response:
                    self.scrape_categories(city_page_response, city_url, city_name)
                else:
                    self.log(
                        f"Response not found for city {city_name} moving to next city..."
                    )

    def scrape_categories(self, response, city_url, city_name):
        resp = Selector(text=response.content)
        self.log(
            f"[{self.processing_country} | {city_name}] Searching Category ###{self.category}### in City Page\n"
        )
        category_page_url_unfiltered = self.get_category_page_url(
            resp, city_url, city_name
        )
        if category_page_url_unfiltered:
            category_page_url = self.update_category_url(category_page_url_unfiltered)
            if category_page_url:
                self.scrape_posts_selenium(category_page_url, city_url, city_name)

    def get_category_page_url(self, resp, base_url, city_name):
        category_xpath = f"//a[contains(@data-alltitle,'{self.category}')]/@href"
        category_page_url = resp.xpath(category_xpath).extract_first()

        if not category_page_url or "#" in category_page_url:
            category_page_url = resp.xpath(
                f"//a[contains(@data-alltitle,'{self.category.lower()}')]/@href"
            ).extract_first()

        if category_page_url and not category_page_url.startswith(("http:", "https:")):
            category_page_url = (
                base_url.rstrip("/") + "/" + category_page_url.lstrip("/")
            )

        if not category_page_url:
            self.log(
                f"[{self.processing_country} | {city_name}] Category ##{self.category}## not found in city page. Moving on to the next city..."
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

    def scrape_posts_selenium(self, category_page_url, city_url, city_name):
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
                paginator = self.driver.find_element(
                    By.CSS_SELECTOR, "div.cl-search-paginator"
                )
                pagination_string = paginator.find_element(
                    By.CSS_SELECTOR, "span.cl-page-number"
                ).text

                parts = pagination_string.split(" ")
                total_items_str = parts[-1].replace(",", "")
                total_items = int(total_items_str)

                num_results = len(post_elements)
                total_pages = math.ceil(total_items / 120)
                self.log(
                    f"[{self.processing_country} | {city_name}] Page {page_num + 1}/{total_pages}: Results Scanning {(120*page_num)+1} - {((120*page_num)+num_results)} / {total_items}"
                )
                if post_elements:
                    self.process_posts(post_elements, city_url, city_name)
                else:
                    self.log(
                        f"[{self.processing_country} | {city_name}] No posts found for '{self.keyword}' in '{self.category}' on page {page_num + 1}/{total_pages}."
                    )
                next_button = paginator.find_element(
                    By.CSS_SELECTOR, "button.bd-button.cl-next-page"
                )
                if "bd-disabled" in next_button.get_attribute("class"):
                    self.log(f"Reached last page in {city_name}")
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
                f"[{self.processing_country} | {city_name}] Error occurred while scraping the category page: {e}"
            )

        finally:
            if self.driver:
                self.driver.quit()

    def process_posts(self, post_elements, city_url, city_name):
        existing_posts = self.google_sheet.get_existing_posts()

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
                    self.log(
                        f"[{self.processing_country} | {city_name}] Title not found: {e}"
                    )
                    continue

                try:
                    url_element = element.find_element(
                        By.CSS_SELECTOR, "div.result-node a.posting-title"
                    )
                    url = url_element.get_attribute("href")
                except Exception as e:
                    self.log(
                        f"[{self.processing_country} | {city_name}] URL not found: {e}"
                    )
                    continue

                try:
                    date_element = element.find_element(
                        By.CSS_SELECTOR, "div.result-node div.meta span[title]"
                    )
                    date = date_element.get_attribute("title")
                except Exception as e:
                    self.log(
                        f"[{self.processing_country} | {city_name}] Date not found: {e}"
                    )
                    continue

                if self.keyword.lower() in title.lower():
                    key = f"{title}-{url}"
                    if key not in existing_posts:
                        self.log(
                            f"Found post: {title} [{self.processing_country} | {city_name}]"
                        )
                        self.google_sheet.save_to_google_sheet(
                            [
                                self.processing_country,
                                city_name,
                                self.category,
                                self.keyword,
                                title,
                                url,
                                date,
                            ]
                        )
                        existing_posts.add(key)
                    else:
                        self.log(
                            f"Duplicate post: {title} [{self.processing_country} | {city_name}]"
                        )
            except Exception as e:
                self.log(
                    f"[{self.processing_country} | {city_name}] Error processing post: {e}"
                )

    def set_params(
        self,
        selected_country,
        selected_canadian_states,
        selected_us_states,
        selected_canadian_cities,
        selected_us_cities,
        keyword,
        category,
    ):
        self.selected_country = selected_country
        self.selected_canadian_states = selected_canadian_states
        self.selected_us_states = selected_us_states
        self.selected_canadian_cities = selected_canadian_cities
        self.selected_us_cities = selected_us_cities
        self.keyword = keyword
        self.category = category

    def run(self):
        self.scraping = True
        self.stop_event.clear()
        self.google_sheet = GoogleSheetController(self.sheet_info, self)
        try:
            self.scrape()

        finally:
            self.scraping = False
            self.stop_event.set()
            self.stop()
            self.log("\nScraping has been completed successfully")

    def stop(self):
        self.stop_event.set()
        self.scraping = False
        self.finished_signal.emit()
        if self.driver:
            self.driver.quit()


# Google Sheet Class and Methods
class GoogleSheetController:
    def __init__(self, sheet_info, scraper):
        self.scraper = scraper
        self.sheet_name = sheet_info.sheet_name
        self.sheet_page_name = sheet_info.sheet_page_name
        self.current_dir = None
        if getattr(sys, "frozen", False):
            self.current_dir = sys._MEIPASS
        else:
            self.current_dir = os.path.dirname(os.path.abspath(__file__))
        self.credentials_file = os.path.join(
            self.current_dir, sheet_info.credentials_file
        )
        self.google_sheet = self.connect_to_google_sheet()
        self.check_connection = self.check_connection(self.google_sheet)

    def check_connection(self, connection):
        if not connection:
            self.scraper.log("Google Sheets connection failed")
            self.scraper.stop()
            return False

    def connect_to_google_sheet(self):
        try:
            # Define the scope for Google Sheets and Google Drive API
            self.scraper.log("Connecting to Google Sheets")
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
            self.scraper.log(
                f"Google Sheets ##{self.sheet_name}## connected successfuly\n"
            )
            return sheet

        except gspread.exceptions.SpreadsheetNotFound:
            self.scraper.log(
                f"The Google Sheet with the name {self.sheet_name} was not found."
            )
            return None

        except gspread.exceptions.WorksheetNotFound:
            self.scraper.log(
                f"The worksheet with the name {self.sheet_page_name} was not found in the Google Sheet."
            )
            return None

        except FileNotFoundError:
            self.scraper.log(
                f"The credentials file {self.credentials_file} was not found."
            )
            return None

        except Exception as e:
            self.scraper.log(
                f"An error occurred while connecting to the Google Sheet: {str(e)}"
            )
            return None

    def get_existing_posts(self):
        existing_posts = set()
        all_posts = self.google_sheet.get_all_values()
        for row in all_posts:
            key = f"{row[4]}-{row[5]}"
            existing_posts.add(key)
        return existing_posts

    def save_to_google_sheet(self, data):
        try:
            self.google_sheet.append_row(data)
            self.scraper.log(f"Successfully saved post to Google Sheet.")
        except Exception as e:
            self.scraper.log(f"Error saving post to Google Sheet: {e}")


class CraigslistScraperUI(QWidget):
    def __init__(self, sheet_info):
        super().__init__()

        self.setWindowTitle("Craigslist Scraper")
        self.resize(800, 600)

        self.sheet_info = sheet_info

        # Country Selection
        self.country_label = QLabel("Select Country:")
        self.country_dropdown = QComboBox(self)
        self.country_dropdown.addItem("Select Country")
        self.country_dropdown.addItem("Canada")
        self.country_dropdown.addItem("US")
        self.country_dropdown.addItem("Canada & US")
        self.country_dropdown.currentIndexChanged.connect(self.on_country_change)

        # State/Province Selection
        self.state_label = QLabel("Select State/Province:")
        self.state_search_input = QLineEdit(self)
        self.state_search_input.setPlaceholderText("Search states/provinces...")

        self.state_search_input.textChanged.connect(self.filter_state_lists)

        self.canadian_state_list = QListWidget(self)
        self.canadian_state_list.setSelectionMode(QListWidget.MultiSelection)
        self.canadian_state_list.itemSelectionChanged.connect(
            self.on_state_selection_changed
        )
        self.us_state_list = QListWidget(self)
        self.us_state_list.setSelectionMode(QListWidget.MultiSelection)
        self.us_state_list.itemSelectionChanged.connect(self.on_state_selection_changed)

        self.select_all_states_checkbox = QCheckBox("Select All States/Provinces", self)
        self.select_all_states_checkbox.setEnabled(False)
        self.select_all_states_checkbox.setChecked(False)
        self.select_all_states_checkbox.stateChanged.connect(
            self.toggle_select_all_states
        )
        self.load_cities_button = QPushButton("Load Cities from Selection", self)
        self.load_cities_button.setEnabled(False)
        self.load_cities_button.clicked.connect(self.on_load_cities_button_click)

        state_layout = QGridLayout()
        state_layout.addWidget(QLabel("Canadian Provinces"), 0, 0)
        state_layout.addWidget(QLabel("US States"), 0, 1)
        state_layout.addWidget(self.canadian_state_list, 1, 0)
        state_layout.addWidget(self.us_state_list, 1, 1)
        state_layout.addWidget(self.select_all_states_checkbox, 2, 0)
        state_layout.addWidget(self.load_cities_button, 2, 1)

        # City Selection
        self.city_label = QLabel("Select City:")
        self.city_search_input = QLineEdit(self)
        self.city_search_input.setPlaceholderText("Search cities...")
        self.city_search_input.textChanged.connect(self.filter_city_lists)

        self.canadian_city_list = QListWidget(self)
        self.canadian_city_list.setSelectionMode(QListWidget.MultiSelection)

        self.us_city_list = QListWidget(self)
        self.us_city_list.setSelectionMode(QListWidget.MultiSelection)

        self.select_all_cities_checkbox = QCheckBox("Select All Cities", self)
        self.select_all_cities_checkbox.setEnabled(False)
        self.select_all_cities_checkbox.stateChanged.connect(
            self.toggle_select_all_cities
        )

        city_layout = QGridLayout()
        city_layout.addWidget(QLabel("Canadian Cities"), 0, 0)
        city_layout.addWidget(QLabel("US Cities"), 0, 1)
        city_layout.addWidget(self.canadian_city_list, 1, 0)
        city_layout.addWidget(self.us_city_list, 1, 1)

        # Keyword and Category Inputs
        self.keyword_label = QLabel("Keyword:")
        self.keyword_input = QLineEdit(self)
        self.category_label = QLabel("Category:")
        self.category_input = QLineEdit(self)

        input_layout = QGridLayout()
        input_layout.addWidget(self.keyword_label, 0, 0)
        input_layout.addWidget(self.keyword_input, 1, 0)
        input_layout.addWidget(self.category_label, 0, 1)
        input_layout.addWidget(self.category_input, 1, 1)

        # Buttons
        self.start_button = QPushButton("Start Scraping", self)
        self.start_button.clicked.connect(self.on_start_button_click)
        self.stop_button = QPushButton("Stop Scraping", self)
        self.stop_button.clicked.connect(self.on_stop_button_click)
        self.stop_button.setEnabled(False)

        form_button_layout = QGridLayout()
        form_button_layout.addWidget(self.start_button, 0, 0)
        form_button_layout.addWidget(self.stop_button, 0, 1)

        # Console Output and Button
        self.clear_console_button = QPushButton("Clear Console")
        self.clear_console_button.clicked.connect(self.on_clear_console_click)
        self.log_output = QTextEdit(self)
        self.log_output.setReadOnly(True)
        consoleLayoutHeader = QHBoxLayout()
        consoleLayoutHeader.addWidget(QLabel("Console Output:"))
        consoleLayoutHeader.addWidget(self.clear_console_button)
        ConsoleLayout = QVBoxLayout()
        ConsoleLayout.addLayout(consoleLayoutHeader)
        ConsoleLayout.addWidget(self.log_output)

        # Layout
        layout = QGridLayout(self)
        formlayout = QVBoxLayout()
        layout.addLayout(formlayout, 0, 0)
        layout.addLayout(ConsoleLayout, 0, 1)

        formlayout.addWidget(self.country_label)
        formlayout.addWidget(self.country_dropdown)
        formlayout.addWidget(self.state_label)
        formlayout.addWidget(self.state_search_input)
        formlayout.addLayout(state_layout)
        formlayout.addWidget(self.city_label)
        formlayout.addWidget(self.city_search_input)
        formlayout.addLayout(city_layout)
        formlayout.addWidget(self.select_all_cities_checkbox)
        formlayout.addLayout(input_layout)
        formlayout.addLayout(form_button_layout)

        self.setLayout(layout)
        self.scraper_thread = CraigslistScraper(self.sheet_info)

    def on_country_change(self):
        selected_country = self.country_dropdown.currentText()
        self.load_states(selected_country)

    def load_states(self, country):
        self.update_log(f"Loading States/Provinces")
        self.canadian_state_list.clear()
        self.us_state_list.clear()
        canadian_states = []
        us_states = []
        self.canadian_city_list.clear()
        self.us_city_list.clear()
        default_response = Selector(text=self.scraper_thread.default_response.content)
        if country == "Canada" or country == "Canada & US":
            canadian_states_elements = default_response.xpath(
                "//h2[contains(text(),'Canada')]//following-sibling::div[1]//h4"
            )
            canadian_states = [
                (state.xpath("text()").get()) for state in canadian_states_elements
            ]
            self.select_all_states_checkbox.setEnabled(True)

        if country == "US" or country == "Canada & US":
            us_states_elements = default_response.xpath(
                "//h2[contains(text(),'US')]//following-sibling::div[1]//h4"
            )
            us_states = [(state.xpath("text()").get()) for state in us_states_elements]
            self.select_all_states_checkbox.setEnabled(True)

        if country == "Select Country":
            self.canadian_state_list.clear()
            self.us_state_list.clear()
            canadian_states = []
            us_states = []
            self.select_all_states_checkbox.setEnabled(False)

        for state in canadian_states:
            self.canadian_state_list.addItem(QListWidgetItem(state))
        for state in us_states:
            self.us_state_list.addItem(QListWidgetItem(state))

        self.load_cities_button.setEnabled(False)
        self.select_all_states_checkbox.setChecked(False)
        self.select_all_cities_checkbox.setEnabled(False)

    def toggle_select_all_states(self, state):
        selected_country = self.country_dropdown.currentText()
        if not selected_country == "Select Country":
            for i in range(self.canadian_state_list.count()):
                item = self.canadian_state_list.item(i)
                item.setSelected(state == 2)

            for i in range(self.us_state_list.count()):
                item = self.us_state_list.item(i)
                item.setSelected(state == 2)

            self.load_cities_button.setEnabled(state == 2)
        else:
            self.select_all_states_checkbox.setChecked(False)
            self.update_log("Please select a country first")

    def on_state_selection_changed(self):
        canadian_items = self.canadian_state_list.selectedItems()
        us_items = self.us_state_list.selectedItems()
        selected_items = canadian_items + us_items
        selected_states = [item.text() for item in selected_items]
        self.canadian_city_list.clear()
        self.us_city_list.clear()
        self.select_all_cities_checkbox.setChecked(False)
        self.select_all_cities_checkbox.setEnabled(False)

        if selected_states:
            self.load_cities_button.setEnabled(True)
        else:
            self.load_cities_button.setEnabled(False)

    def filter_state_lists(self):
        search_text = self.state_search_input.text().lower()

        # Filter Canadian states list
        for i in range(self.canadian_state_list.count()):
            item = self.canadian_state_list.item(i)
            item.setHidden(search_text not in item.text().lower())

        # Filter US states list
        for i in range(self.us_state_list.count()):
            item = self.us_state_list.item(i)
            item.setHidden(search_text not in item.text().lower())

    def on_load_cities_button_click(self):
        self.update_log("Loading cities ...")
        country = self.country_dropdown.currentText()
        self.canadian_city_list.clear()
        self.us_city_list.clear()
        canadian_cities = []
        us_cities = []
        canadian_states = [
            item.text() for item in self.canadian_state_list.selectedItems()
        ]
        us_states = [item.text() for item in self.us_state_list.selectedItems()]
        default_response = Selector(text=self.scraper_thread.default_response.content)
        if country == "Canada" or country == "Canada & US":
            for canadian_state in canadian_states:
                canadian_city_elements = default_response.xpath(
                    f"//h2[contains(text(),'Canada')]//following-sibling::div[1]//h4[contains(text(),'{canadian_state}')]//following-sibling::ul[1]/li/a"
                )
                canadian_cities += [
                    (city.xpath("text()").get(), city.xpath("@href").get())
                    for city in canadian_city_elements
                ]
        if country == "US" or country == "Canada & US":
            for us_state in us_states:
                us_city_elements = default_response.xpath(
                    f"//h2[contains(text(),'US')]//following-sibling::div[1]//h4[contains(text(),'{us_state}')]//following-sibling::ul[1]/li/a"
                )
                us_cities += [
                    (city.xpath("text()").get(), city.xpath("@href").get())
                    for city in us_city_elements
                ]
        if country == "Select Country":
            self.canadian_city_list.clear()
            self.us_city_list.clear()
            canadian_cities = []
            us_cities = []
            self.select_all_cities_checkbox.setEnabled(False)
        for index, (city_name, city_url) in enumerate(canadian_cities, start=1):
            item = QListWidgetItem(city_name)
            item.setData(Qt.UserRole, city_url)
            self.canadian_city_list.addItem(item)
        for index, (city_name, city_url) in enumerate(us_cities, start=1):
            item = QListWidgetItem(city_name)
            item.setData(Qt.UserRole, city_url)
            self.us_city_list.addItem(item)

        self.select_all_cities_checkbox.setChecked(False)
        self.select_all_cities_checkbox.setEnabled(True)

    def toggle_select_all_cities(self, state):
        selected_country = self.country_dropdown.currentText()
        if not selected_country == "Select Country":
            for i in range(self.canadian_city_list.count()):
                item = self.canadian_city_list.item(i)
                item.setSelected(state == 2)

            for i in range(self.us_city_list.count()):
                item = self.us_city_list.item(i)
                item.setSelected(state == 2)

        else:
            self.select_all_cities_checkbox.setChecked(False)
            self.select_all_cities_checkbox.setEnabled(False)
            self.update_log("Please select a country first")

    def filter_city_lists(self):
        search_text = self.city_search_input.text().lower()

        # Filter Canadian states list
        for i in range(self.canadian_city_list.count()):
            item = self.canadian_city_list.item(i)
            item.setHidden(search_text not in item.text().lower())

        # Filter US states list
        for i in range(self.us_city_list.count()):
            item = self.us_city_list.item(i)
            item.setHidden(search_text not in item.text().lower())

    def on_start_button_click(self):
        selected_country = self.country_dropdown.currentText()
        selected_canadian_states = [
            item.text() for item in self.canadian_state_list.selectedItems()
        ]
        selected_us_states = [
            item.text() for item in self.us_state_list.selectedItems()
        ]
        selected_canadian_cities = [
            item for item in self.canadian_city_list.selectedItems()
        ]
        selected_us_cities = [item for item in self.us_city_list.selectedItems()]
        keyword = self.keyword_input.text()
        category = self.category_input.text()
        if selected_country == "Select Country":
            self.update_log("Please select a Country Value.")
            return
        if len(selected_us_states + selected_canadian_states) < 1:
            self.update_log("Please select State/Provice.")
            return
        if len(selected_us_cities + selected_canadian_cities) < 1:
            self.update_log("Please select City.")
            return
        if not keyword:
            self.update_log("Please enter a keyword.")
            return
        if not category:
            self.update_log("Please select a category.")
            return
        if self.scraper_thread and self.scraper_thread.isRunning():
            return
        self.update_log("Scraper Initializing...")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.scraper_thread = CraigslistScraper(self.sheet_info)
        self.scraper_thread.set_params(
            selected_country,
            selected_canadian_states,
            selected_us_states,
            selected_canadian_cities,
            selected_us_cities,
            keyword,
            category,
        )
        self.scraper_thread.log_signal.connect(self.update_log)
        self.scraper_thread.finished_signal.connect(self.on_scraper_finished)
        self.scraper_thread.start()
        self.update_log("Scraping thread started...")

    def on_stop_button_click(self):
        if self.scraper_thread is not None and self.scraper_thread.isRunning():
            self.scraper_thread.stop_event.set()
            self.scraper_thread.quit()
            self.scraper_thread.wait()
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def on_scraper_finished(self):
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.update_log("\nScraper Stopped.")

    def on_clear_console_click(self):
        self.log_output.clear()

    def update_log(self, message):
        self.log_output.append(message)


def main():
    SheetInfo = namedtuple(
        "SheetInfo", ["credentials_file", "sheet_name", "sheet_page_name"]
    )
    sheet_info = SheetInfo(
        credentials_file="credentials.json",
        sheet_name="Craigslist Scraper",
        sheet_page_name="Sheet1",
    )
    app = QApplication(sys.argv)
    window = CraigslistScraperUI(sheet_info)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

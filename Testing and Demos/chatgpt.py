from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import csv
import os
import re


class Craigslist:
    file_path = "Data.csv"
    country = "Canada"

    def __init__(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.set_page_load_timeout(10)

    def target_url(self, url):
        n = 0
        while n < 3:
            try:
                self.driver.get(url)
                status_code = 200  # Selenium does not return status codes
                print("Status Code: ", status_code)
                print(f"Request Number/Total Request: {n}/3")
                print()
                if status_code == 200:
                    self.run_main()
                    break
            except TimeoutException:
                status_code = 408
                print()
                print("Retrying request failed due to getting blocked or timeout")
                print("Error Code", status_code)
                print()
            n += 1
        else:
            print("Failed to get a successful response after 3 attempts")

    def run_main(self):
        if "CA" in self.driver.current_url:
            self.country = "Canada"
        else:
            self.country = "US"
        print()

        total_cities = self.driver.find_elements(
            By.XPATH,
            f"//h2[contains(text(),'{self.country}')]//following-sibling::div[1]//ul/li/a",
        )
        for city_count, city_element in enumerate(total_cities, start=1):
            city_url = city_element.get_attribute("href")
            print()
            print("Currently Scraping City: ", city_url)
            print(
                f"Current Number/Total Number of cities: {city_count}/{len(total_cities)}"
            )
            try:
                self.driver.get(city_url)
                self.categories(city_url)
            except TimeoutException:
                print(f"Timeout occurred while accessing {city_url}. Skipping.")

    def categories(self, city_url):
        with open("input.csv", "r", encoding="utf-8") as input_file:
            reader = csv.reader(input_file, delimiter=",")
            for i in reader:
                category = str(i[0])
                keyword = str(i[1])
                try:
                    category_element = self.driver.find_element(
                        By.XPATH, f"//a[contains(@data-alltitle,'{category}')]"
                    )
                    category_page = category_element.get_attribute("href")
                except NoSuchElementException:
                    try:
                        category_element = self.driver.find_element(
                            By.XPATH,
                            f"//a[contains(@data-alltitle,'{category.lower()}')]",
                        )
                        category_page = category_element.get_attribute("href")
                    except NoSuchElementException:
                        print(
                            f"Could not find a page for category {category}. Skipping."
                        )
                        continue

                if not category_page.startswith(("http:", "https:")):
                    category_page = re.sub(r"^\/", "", category_page)
                    category_page = str(city_url) + category_page.strip()

                print("Scraped Category", category_page)
                try:
                    self.driver.get(category_page)
                    self.scrap(category, keyword, city_url)
                except TimeoutException:
                    print(
                        f"Timeout occurred while accessing {category_page}. Skipping."
                    )

    def scrap(self, category, keyword, city):
        page_num = 0  # Start from page 0
        base_url = self.driver.current_url

        while True:
            print(f"Scraping page {page_num + 1} of {category} in {city}")

            if "#search=" not in base_url:
                base_url += "#search=1~thumb~0~0"

            current_url = re.sub(r"~\d+~0", f"~{page_num}~0", base_url)
            print(f"Scraping URL: {current_url}")
            try:
                self.driver.get(current_url)
                if not self.check_csv_file_exist():
                    self.create_csv_file()
                    self.add_urls(category, keyword, city)
                else:
                    print("File already exists")
                    self.check_current_urls_exist_in_csv(category, keyword, city)

                next_page_link = self.get_next_page_link(page_num)
                if next_page_link:
                    page_num += 1
                else:
                    break
            except TimeoutException:
                print(f"Timeout occurred while accessing {current_url}. Skipping.")
                break

    def get_next_page_link(self, page_num):
        print("Inside Next Page code")
        current_url = self.driver.current_url
        print(f"Currently Scraping URL: {current_url}")

        try:
            next_page_button = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "button.cl-next-page:not(.bd-disabled)")
                )
            )
            print("Next Page button found")
            next_page_num = page_num + 1
            next_page_url = re.sub(r"~\d+~0", f"~{next_page_num}~0", current_url)
            print(f"Next Page URL is: {next_page_url}")
            return next_page_url
        except TimeoutException:
            print(
                "No next page button found, checking total results for alternative pagination."
            )
            total_results_text = self.driver.find_element(
                By.CSS_SELECTOR, ".cl-page-number"
            ).text
            total_results_match = re.search(
                r"(\d+) - (\d+) of (\d+)", total_results_text
            )
            if total_results_match:
                start, end, total = map(int, total_results_match.groups())
                if end < total:
                    next_page_num = page_num + 1
                    next_page_url = re.sub(
                        r"~\d+~0", f"~{next_page_num}~0", current_url
                    )
                    print(f"Next Page URL by total results is: {next_page_url}")
                    return next_page_url
            return None

    def check_current_urls_exist_in_csv(self, category, keyword, city):
        links = []
        post_titles = []

        xpaths = [
            f"//div[@class='title' and contains(text(),'{keyword}')]/parent::a",
            f"//div[@class='title' and contains(text(),'{keyword.lower()}')]/parent::a",
            f"//div[@class='title' and contains(text(),'{keyword.title()}')]/parent::a",
        ]

        for keyword_xpath in xpaths:
            post_links = self.driver.find_elements(By.XPATH, keyword_xpath)
            for li in post_links:
                link = li.get_attribute("href")
                post_title = li.find_element(By.XPATH, ".//div").text
                if link not in links:
                    links.append(link)
                    post_titles.append(post_title)

        existing_urls = {}
        with open(self.file_path, "r", newline="", encoding="utf-8") as input_file:
            reader = csv.reader(input_file, delimiter=",")
            for row in reader:
                existing_urls[row[6]] = row[5]

        for idx, url in enumerate(links):
            post_title = post_titles[idx]
            if url in existing_urls and existing_urls[url] == post_title:
                print("URL already exists:", url)
            else:
                self.add_url_to_csv(city, category, keyword, post_title, url)

    def add_urls(self, category, keyword, city):
        links = []
        post_titles = []

        xpaths = [
            f"//div[@class='title' and contains(text(),'{keyword}')]/parent::a",
            f"//div[@class='title' and contains(text(),'{keyword.lower()}')]/parent::a",
            f"//div[@class='title' and contains(text(),'{keyword.title()}')]/parent::a",
        ]

        for keyword_xpath in xpaths:
            post_links = self.driver.find_elements(By.XPATH, keyword_xpath)
            for li in post_links:
                link = li.get_attribute("href")
                post_title = li.find_element(By.XPATH, ".//div").text
                if link not in links:
                    links.append(link)
                    post_titles.append(post_title)

        for idx, link in enumerate(links):
            post_title = post_titles[idx]
            self.add_url_to_csv(city, category, keyword, post_title, link)

    def create_csv_file(self):
        with open(self.file_path, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(
                [
                    "Country",
                    "City",
                    "City Link",
                    "Category",
                    "Keyword",
                    "Post_title",
                    "Link",
                ]
            )
        print(f"File '{self.file_path}' created.")

    def check_csv_file_exist(self):
        if os.path.exists(self.file_path):
            print(f"File '{self.file_path}' already exists.")
            return True
        return False

    def add_url_to_csv(self, city, category, keyword, post_title, link):
        if city:
            match = re.search(r"\/\/([^\.]+)", city)
            city_link = match.group(1) if match else city
        else:
            city_link = None

        with open(self.file_path, "a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(
                [self.country, city, city_link, category, keyword, post_title, link]
            )
        print(f"Added URL to CSV: {link}")


if __name__ == "__main__":
    scraper = Craigslist()
    scraper.target_url("https://www.craigslist.org/about/sites")

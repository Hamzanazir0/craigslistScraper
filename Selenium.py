# No Full Response for pagination otherwise fine

import requests
import os
import csv
from scrapy.selector import Selector
from bs4 import BeautifulSoup
import re
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select

# import chromedriver_binary
from selenium import webdriver
import time


class Craigslist:
    file_path = "Data.csv"
    country = "Canada"
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
        "DNT": "1",
        # 'Cookie': 'cl_b=4|eeb6f8079f6ae70ff6ef79827c253becec2c287e|17105056420C0Qo; cl_def_hp=toronto',
        # 'If-Modified-Since': 'Tue, 27 Feb 2024 14:42:31 GMT',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }

    def start(self):
        options = Options()
        options.add_experimental_option("detach", True)
        # options.binary_location = r"C:/Program Files/Google/Chrome/Application/chrome.exe"
        # options.binary_location = "C:\Program Files\Google\Chrome\Application\chrome.exe"
        # options.add_argument("--headless")
        # options.add_argument("--no-sandbox")
        # options.add_argument('--disable-gpu')

        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36"
        )
        options.add_argument("start-maximized")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-extensions")  # Disable extensions
        options.add_argument(
            "--disable-infobars"
        )  # Disable the "Chrome is being controlled by automated test software" infobar
        options.add_argument("--ignore-certificate-errors")
        self.driver = webdriver.Chrome(options=options)

    def target_url(self, url):
        n = 0
        while n < 3:
            response = requests.get(
                url,
                headers=self.headers,
            )
            status_code = response.status_code
            print("Status Code: ", status_code)
            print(f"Request Number/Total Request: {n}/3")
            print()
            if status_code == 200:
                self.run_main(response)
                break
            else:
                print()
                print("Retrying request failed due to getting blocked")
                print("Error Code", status_code)
                print()
            n += 1
        else:
            print("Failed to get a successful response after 3 attempts")

    def run_main(self, response):
        resp = Selector(text=response.content)
        city_count = 1
        if "CA" in response.url:
            self.country = "Canada"
        else:
            self.country = "US"
        print()
        total_cities = resp.xpath(
            "//h2[contains(text(),'"
            + str(self.country)
            + "')]//following-sibling::div[1]//ul/li/a/@href"
        ).getall()
        for city in total_cities:
            print()
            print("Currently Scraping City: ", city)
            print(
                f"Current Number/Total Number of cities: {city_count}/{len(total_cities)}"
            )
            response = requests.get(
                str(city).strip(),
                headers=self.headers,
            )
            city_count = city_count + 1
            self.categories(response, city)  # Renamed method to correct spelling

    def categories(self, response, city):
        resp = Selector(text=response.content)
        url = response.url

        with open("input.csv", "r", encoding="utf-8") as input_file:
            reader = csv.reader(input_file, delimiter=",")
            for i in reader:
                category = str(i[0])
                keyword = str(i[1])
                category_xpath = (
                    "//a[contains(@data-alltitle,'" + category + "')]/@href"
                )
                category_page = resp.xpath(category_xpath).extract_first()
                print("Currently Scraping Category", category)

                if not category_page or "#" in str(category_page).strip():
                    category_xpath = (
                        "//a[contains(@data-alltitle,'"
                        + str(category).strip().lower()
                        + "')]/@href"
                    )
                    category_page = resp.xpath(category_xpath).extract_first()

                if not category_page:
                    print(f"Could not find a page for category {category}. Skipping.")
                    continue

                if not category_page.startswith(("http:", "https:")):
                    category_page = re.sub(r"^\/", "", str(category_page))
                    category_page = str(url) + str(category_page).strip()

                if "#search=" not in category_page:
                    category_page += "#search=1~thumb~0~0"

                print("Scraped Category", category_page)

                self.driver.get(category_page)
                time.sleep(7)
                html = self.driver.page_source
                response = Selector(text=html)

                self.next_page_button(category, keyword, response, city)

    ###########################

    def next_page_button(self, category, keyword, response, city):
        self.scrap(category, keyword, response, city)
        button_check = response.xpath(
            "//button[@class='bd-button cl-next-page icon-only bd-disabled']/@class"
        ).extract_first()
        if button_check:
            None
        else:
            self.driver.find_elements(
                By.XPATH, "//button[@class='bd-button cl-next-page icon-only']"
            )[0].click()
            time.sleep(6)
            html = self.driver.page_source
            response = Selector(text=html)
            self.next_page_button(category, keyword, response, city)

    def scrap(self, category, keyword, response, city):
        search_results = response.css("li.cl-static-search-result")
        num_results = len(search_results)
        print(f"Number of search results: {num_results}")

        # Process the page
        if not self.check_csv_file_exist():
            self.create_csv_file()
            self.add_urls(category, keyword, response, city)
        else:
            print("File already exists")
            self.check_current_urls_exist_in_csv(category, keyword, response, city)

    ###########################
    def check_current_urls_exist_in_csv(self, category, keyword, response, city):
        resp = response
        links = []
        post_titles = []
        xpaths = [
            "//div[@class='title' and contains(text(),'"
            + str(keyword)
            + "')]/parent::a",
            "//div[@class='title' and contains(text(),'"
            + str(keyword).lower()
            + "')]/parent::a",
            "//div[@class='title' and contains(text(),'"
            + str(keyword).title()
            + "')]/parent::a",
        ]

        for keyword_xpath in xpaths:
            post_links = resp.xpath(keyword_xpath)
            for li in post_links:
                link = li.xpath(".//@href").extract_first()
                post_title = li.xpath(".//div/text()").extract_first()
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

    def add_urls(self, category, keyword, response, city):
        resp = response
        links = []
        post_titles = []
        xpaths = [
            "//div[@class='title' and contains(text(),'"
            + str(keyword)
            + "')]/parent::a",
            "//div[@class='title' and contains(text(),'"
            + str(keyword).lower()
            + "')]/parent::a",
            "//div[@class='title' and contains(text(),'"
            + str(keyword).title()
            + "')]/parent::a",
        ]

        for keyword_xpath in xpaths:
            post_links = resp.xpath(keyword_xpath)
            for li in post_links:
                link = li.xpath(".//@href").extract_first()
                post_title = li.xpath(".//div/text()").extract_first()
                if link not in links:  # Check if link is not already in links
                    links.append(link)
                    post_titles.append(post_title)

        # Now links and post_titles should contain unique values
        for idx, link in enumerate(links):
            post_title = post_titles[idx]  # Get corresponding post title
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
            match = re.search(r"\/\/([^\.]+)", str(city))
            if match:
                city_link = match.group(1)
            else:
                city_link = city  # Fallback to using the full city URL
        else:
            city_link = None
        with open(self.file_path, "a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(
                [self.country, city_link, city, category, keyword, post_title, link]
            )

    def exit(self):
        self.driver.quit()


if __name__ == "__main__":
    scraper = Craigslist()
    urls = [
        "https://www.craigslist.org/about/sites#CA",
        "https://www.craigslist.org/about/sites#USA",
    ]
    for url in urls:
        scraper.start()
        scraper.target_url(url)
        scraper.exit()

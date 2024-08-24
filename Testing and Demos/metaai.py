import requests
import os
import csv
from scrapy.selector import Selector
import re
import random
import time
from urllib.parse import urlparse


class CraigslistScraper:
    def __init__(self):
        self.file_path = "Data.csv"
        self.country = "Canada"
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/110.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        ]
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

    def get_random_user_agent(self):
        return random.choice(self.user_agents)

    def send_request(self, url, max_retries=3):
        for attempt in range(max_retries):
            try:
                self.headers["User-Agent"] = self.get_random_user_agent()
                response = requests.get(url, headers=self.headers)
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                print(f"Request failed: {e}")
                time.sleep(2**attempt)
        return None

    def parse_html(self, response):
        return Selector(text=response.content)

    def extract_data(self, response, keyword, city):
        resp = self.parse_html(response)
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
        if os.path.exists(self.file_path):
            with open(self.file_path, "r", newline="", encoding="utf-8") as input_file:
                reader = csv.reader(input_file, delimiter=",")
                for row in reader:
                    existing_urls[row[6]] = row[5]

        for idx, url in enumerate(links):
            post_title = post_titles[idx]
            if url in existing_urls and existing_urls[url] == post_title:
                print("URL already exists:", url)
            else:
                self.write_to_csv(
                    self.country, city, city, "Category", keyword, post_title, url
                )

    def write_to_csv(
        self, country, city, city_link, category, keyword, post_title, link
    ):
        with open(self.file_path, "a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(
                [country, city, city_link, category, keyword, post_title, link]
            )

    def create_csv_file(self):
        if not os.path.exists(self.file_path):
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

    def run(self):
        self.create_csv_file()
        urls = [
            "https://www.craigslist.org/about/sites#CA",
            "https://www.craigslist.org/about/sites#USA",
        ]
        keyword = input("Enter the keyword: ")
        category = input("Enter the category: ")
        for url in urls:
            response = self.send_request(url)
            if response:
                resp = self.parse_html(response)
                if "CA" in response.url:
                    self.country = "Canada"
                else:
                    self.country = "US"
                total_cities = resp.xpath(
                    "//h2[contains(text(),'"
                    + str(self.country)
                    + "')]//following-sibling::div[1]//ul/li/a/@href"
                ).getall()
                for city in total_cities:
                    print()
                    print("Currently Scraping City: ", city)
                    city_response = self.send_request(city)
                    if city_response:
                        self.extract_data(city_response, keyword, city, category)


if __name__ == "__main__":
    scraper = CraigslistScraper()
    scraper.run()

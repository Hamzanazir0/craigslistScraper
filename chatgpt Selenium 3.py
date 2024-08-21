# Selenium with pagination google sheets duplication check and error handling complete console code.

import requests
import gspread
import csv
import re
from oauth2client.service_account import ServiceAccountCredentials
from scrapy.selector import Selector
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urlparse, urlunparse


class CraigslistScraper:
    def __init__(self, sheet_name, credentials_file):
        self.sheet_name = sheet_name
        self.credentials_file = credentials_file
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
        sheet = client.open(self.sheet_name).sheet1

        # Add headers if they do not exist
        if not sheet.row_values(1):
            headers = [
                "Country",
                "City",
                "City Link",
                "Category",
                "Keyword",
                "Post_title",
                "Link",
                "Date",
            ]
            sheet.insert_row(headers, 1)

        return sheet

    def fetch_url(self, url, retries=3):
        for attempt in range(retries):
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                return response
            else:
                print(
                    f"[Retry {attempt + 1}/{retries}] Failed to fetch {url} - Status Code: {response.status_code}"
                )
        print(
            f"[Error] Failed to get a successful response after {retries} attempts for {url}"
        )
        return None

    def scrape(self, url):
        response = self.fetch_url(url)
        if not response:
            return

        self.country = "Canada" if "CA" in response.url else "US"
        resp = Selector(text=response.content)

        city_urls = resp.xpath(
            f"//h2[contains(text(),'{self.country}')]//following-sibling::div[1]//ul/li/a/@href"
        ).getall()
        print(f"[{self.country}] Found {len(city_urls)} cities to scrape.")

        for index, city_url in enumerate(city_urls, start=1):
            print(
                f"[{self.country}] Scraping city {index}/{len(city_urls)}: {city_url}"
            )
            response = self.fetch_url(city_url)
            if response:
                self.scrape_categories(response, city_url)

    def scrape_categories(self, response, city_url):
        resp = Selector(text=response.content)

        with open("input.csv", "r", encoding="utf-8") as input_file:
            reader = csv.reader(input_file)

            for category, keyword in reader:
                print(f"[{self.country}] Scraping Category: {category}")

                category_page_url_unfiltered = self.get_category_page_url(
                    resp, category, city_url
                )
                if category_page_url_unfiltered:
                    category_page_url = self.update_category_url(
                        category_page_url_unfiltered
                    )
                    if category_page_url:
                        print(
                            f"[{self.country}] Found Category URL: {category_page_url}"
                        )
                        self.scrape_posts_selenium(
                            category, keyword, category_page_url, city_url
                        )
                else:
                    print(
                        f"[{self.country}] Skipping category '{category}' due to missing page."
                    )
                    continue

    def get_category_page_url(self, resp, category, base_url):
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
            print(
                f"[{self.country}] Category page not found for '{category}'. Moving on to the next category..."
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

    def scrape_posts_selenium(self, category, keyword, category_page_url, city_url):
        driver = webdriver.Chrome()
        driver.get(category_page_url)
        page_num = 0

        try:
            while True:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "li.cl-search-result")
                    )
                )
                post_elements = driver.find_elements(
                    By.CSS_SELECTOR, "li.cl-search-result"
                )

                num_results = len(post_elements)
                print(
                    f"[{self.country}] Page {page_num + 1}: Found {num_results} posts in '{category}' for '{keyword}'."
                )

                if post_elements:
                    self.process_posts(category, keyword, post_elements, city_url)
                else:
                    print(
                        f"[{self.country}] No posts found for '{keyword}' in '{category}' on page {page_num + 1}."
                    )

                paginator = driver.find_element(
                    By.CSS_SELECTOR, "div.cl-search-paginator"
                )
                next_button = paginator.find_element(
                    By.CSS_SELECTOR, "button.bd-button.cl-next-page"
                )

                if "bd-disabled" in next_button.get_attribute("class"):
                    print(
                        f"[{self.country}] Reached last page in '{category}' for '{keyword}'. Moving to next city..."
                    )
                    break

                next_button.click()
                page_num += 1
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "li.cl-search-result")
                    )
                )

        except Exception as e:
            print(
                f"[{self.country}] Error occurred while scraping the category page: {e}"
            )

        finally:
            driver.quit()

    def process_posts(self, category, keyword, post_elements, city_url):
        existing_posts = self.get_existing_posts()

        for element in post_elements:
            try:
                try:
                    title_element = element.find_element(
                        By.CSS_SELECTOR, "div.result-node a.posting-title span.label"
                    )
                    title = title_element.text.strip()
                except Exception as e:
                    print(f"[{self.country}] Title not found: {e}")
                    continue

                try:
                    url_element = element.find_element(
                        By.CSS_SELECTOR, "div.result-node a.posting-title"
                    )
                    url = url_element.get_attribute("href")
                except Exception as e:
                    print(f"[{self.country}] URL not found: {e}")
                    continue

                try:
                    date_time_element = element.find_element(
                        By.CSS_SELECTOR, "div.result-node div.meta span[title]"
                    )
                    date_time = date_time_element.get_attribute("title").strip()
                except Exception as e:
                    print(f"[{self.country}] Date/Time not found: {e}")
                    continue

                key = (title, city_url)  # Create a key with title and city_url

                if keyword.lower() in title.lower():
                    if key not in existing_posts:
                        self.add_post_to_google_sheet(
                            city_url,
                            category,
                            keyword,
                            {"title": title, "url": url, "date_time": date_time},
                        )
                        existing_posts[key] = url
                        print(f"[{self.country}] New post added: {title} in {city_url}")
                    else:
                        print(
                            f"[{self.country}] Duplicate post skipped: {title} in {city_url}"
                        )

            except Exception as e:
                print(f"[{self.country}] Error processing post: {e}")

    def get_existing_posts(self):
        existing_posts = {}
        records = self.google_sheet.get_all_records()
        for record in records:
            key = (
                record["Post_title"],
                record["City Link"],
            )  # Using a tuple of post title and city as the key
            existing_posts[key] = record["Link"]
        return existing_posts

    def add_post_to_google_sheet(self, city_url, category, keyword, post_details):
        city_name = re.search(r"\/\/([^\.]+)", city_url).group(1) if city_url else None
        new_row = [
            self.country,
            city_name,
            city_url,
            category,
            keyword,
            post_details["title"],
            post_details["url"],
            post_details["date_time"],
        ]
        self.google_sheet.append_row(new_row)


if __name__ == "__main__":
    sheet_name = "Craigslist Scraper Results"
    credentials_file = "credentials.json"

    scraper = CraigslistScraper(sheet_name, credentials_file)
    urls = [
        "https://www.craigslist.org/about/sites#CA",
        "https://www.craigslist.org/about/sites#USA",
    ]
    for url in urls:
        scraper.scrape(url)

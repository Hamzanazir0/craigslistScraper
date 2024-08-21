# Chat GPT improved with Data Structures and Functions no duplication saved
# Working code with google sheets no duplications

import requests
import gspread
import csv
from oauth2client.service_account import ServiceAccountCredentials
from google.oauth2.service_account import Credentials
from scrapy.selector import Selector
import re


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
                    f"Retrying... ({attempt + 1}/{retries}) - Status Code: {response.status_code}"
                )
        print("Failed to get a successful response after multiple attempts")
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
        print(f"Found {len(city_urls)} cities in {self.country}")

        for index, city_url in enumerate(city_urls, start=1):
            print(f"Scraping city {index}/{len(city_urls)}: {city_url}")
            response = self.fetch_url(city_url)
            if response:
                self.scrape_categories(response, city_url)

    def scrape_categories(self, response, city_url):
        resp = Selector(text=response.content)

        with open("input.csv", "r", encoding="utf-8") as input_file:
            reader = csv.reader(input_file)
            for category, keyword in reader:
                print(f"Scraping Category: {category}")
                category_page_url = self.get_category_page_url(resp, category, city_url)
                if category_page_url:
                    print(f"Scraped Category URL: {category_page_url}")
                    response = self.fetch_url(category_page_url)
                    if response:
                        self.scrape_posts(category, keyword, response, city_url)

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
            print(f"Category page not found for '{category}'")

        return category_page_url

    def scrape_posts(self, category, keyword, response, city_url):
        resp = Selector(text=response.content)
        post_elements = resp.css("li.cl-static-search-result")

        if post_elements:
            self.process_posts(category, keyword, post_elements, city_url)
        else:
            print(f"No posts found for keyword '{keyword}' in category '{category}'")

    def process_posts(self, category, keyword, post_elements, city_url):
        existing_posts = self.get_existing_posts()
        new_posts = self.extract_posts(post_elements, keyword)

        for post in new_posts:
            # Check if the title already exists in the existing posts
            if any(
                existing_title == post["title"]
                for existing_title in existing_posts.values()
            ):
                print(f"Duplicate post found and skipped: {post['title']}")
            else:
                self.add_post_to_google_sheet(city_url, category, keyword, post)
                existing_posts[post["url"]] = post[
                    "title"
                ]  # Add the new post to the existing posts dictionary

    def extract_posts(self, post_elements, keyword):
        posts = []
        for element in post_elements:
            title = element.css(".title::text").get()
            url = element.css("a::attr(href)").get()
            if keyword.lower() in title.lower():
                posts.append({"title": title, "url": url})
        return posts

    def get_existing_posts(self):
        existing_posts = {}
        records = self.google_sheet.get_all_records()
        for record in records:
            existing_posts[record["Link"]] = record["Post_title"]
        return existing_posts

    def add_post_to_google_sheet(self, city_url, category, keyword, post):
        city_name = re.search(r"\/\/([^\.]+)", city_url).group(1) if city_url else None
        row = [
            self.country,
            city_name,
            city_url,
            category,
            keyword,
            post["title"],
            post["url"],
        ]
        self.google_sheet.append_row(row)
        print(f"Added post to Google Sheet: {post['title']}")


if __name__ == "__main__":
    sheet_name = "Craigslist Scraper Results"
    credentials_file = "C:/Users/hamza/Downloads/craiglist/credentials.json"

    scraper = CraigslistScraper(sheet_name, credentials_file)
    urls = [
        "https://www.craigslist.org/about/sites#CA",
        "https://www.craigslist.org/about/sites#USA",
    ]
    for url in urls:
        scraper.scrape(url)

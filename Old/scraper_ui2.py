import tkinter as tk
from tkinter import scrolledtext
from threading import Thread
import requests
import gspread
import csv
from oauth2client.service_account import ServiceAccountCredentials
from scrapy.selector import Selector
import re


class CraigslistScraperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Craigslist Scraper")
        self.is_scraping = False

        # Keyword Input
        self.keyword_label = tk.Label(root, text="Keyword:")
        self.keyword_label.grid(row=0, column=0, padx=10, pady=10)
        self.keyword_entry = tk.Entry(root, width=30)
        self.keyword_entry.grid(row=0, column=1, padx=10, pady=10)

        # Category Input
        self.category_label = tk.Label(root, text="Category:")
        self.category_label.grid(row=1, column=0, padx=10, pady=10)
        self.category_entry = tk.Entry(root, width=30)
        self.category_entry.grid(row=1, column=1, padx=10, pady=10)

        # Submit Button
        self.submit_button = tk.Button(
            root, text="Start Scraper", command=self.toggle_scraper
        )
        self.submit_button.grid(row=2, column=0, padx=10, pady=10)

        # Clear Console Button
        self.clear_console_button = tk.Button(
            root, text="Clear Console", command=self.clear_console
        )
        self.clear_console_button.grid(row=2, column=1, padx=10, pady=10)

        # Console Output
        self.console_output = scrolledtext.ScrolledText(
            root, wrap=tk.WORD, width=70, height=20
        )
        self.console_output.grid(row=3, column=0, columnspan=2, padx=10, pady=10)

    def toggle_scraper(self):
        if not self.is_scraping:
            keyword = self.keyword_entry.get().strip()
            category = self.category_entry.get().strip()

            if not keyword or not category:
                self.log("Please enter both keyword and category.")
                return

            self.submit_button.config(text="Stop Scraper")
            self.is_scraping = True
            self.log("Scraper is starting...")

            # Start scraper in a separate thread
            scraper_thread = Thread(target=self.run_scraper, args=(keyword, category))
            scraper_thread.start()
        else:
            self.is_scraping = False
            self.submit_button.config(text="Start Scraper")
            self.log("Scraper is stopped.")

    def run_scraper(self, keyword, category):
        scraper = CraigslistScraper(
            "Craigslist Scraper Results",
            "credentials.json",
            self,
        )
        urls = [
            "https://www.craigslist.org/about/sites#CA",
            "https://www.craigslist.org/about/sites#USA",
        ]
        for url in urls:
            if not self.is_scraping:
                break
            scraper.scrape(url, category, keyword)

        self.is_scraping = False
        self.submit_button.config(text="Start Scraper")
        self.log("Scraper is stopped.")

    def clear_console(self):
        self.console_output.delete(1.0, tk.END)

    def log(self, message):
        self.console_output.insert(tk.END, message + "\n")
        self.console_output.see(tk.END)


class CraigslistScraper:
    def __init__(self, sheet_name, credentials_file, app):
        self.sheet_name = sheet_name
        self.credentials_file = credentials_file
        self.app = app
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
                self.app.log(
                    f"Retrying... ({attempt + 1}/{retries}) - Status Code: {response.status_code}"
                )
        self.app.log("Failed to get a successful response after multiple attempts")
        return None

    def scrape(self, url, category, keyword):
        response = self.fetch_url(url)
        if not response:
            return

        self.country = "Canada" if "CA" in response.url else "US"
        resp = Selector(text=response.content)

        city_urls = resp.xpath(
            f"//h2[contains(text(),'{self.country}')]//following-sibling::div[1]//ul/li/a/@href"
        ).getall()
        self.app.log(f"Found {len(city_urls)} cities in {self.country}")

        for index, city_url in enumerate(city_urls, start=1):
            if not self.app.is_scraping:
                break
            self.app.log(f"Scraping city {index}/{len(city_urls)}: {city_url}")
            response = self.fetch_url(city_url)
            if response:
                self.scrape_categories(response, city_url, category, keyword)

    def scrape_categories(self, response, city_url, category, keyword):
        resp = Selector(text=response.content)

        self.app.log(f"Scraping Category: {category}")
        category_page_url = self.get_category_page_url(resp, category, city_url)
        if category_page_url:
            self.app.log(f"Scraped Category URL: {category_page_url}")
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
            self.app.log(f"Category page not found for '{category}'")

        return category_page_url

    def scrape_posts(self, category, keyword, response, city_url):
        resp = Selector(text=response.content)
        post_elements = resp.css("li.cl-static-search-result")

        if post_elements:
            self.process_posts(category, keyword, post_elements, city_url)
        else:
            self.app.log(
                f"No posts found for keyword '{keyword}' in category '{category}'"
            )

    def process_posts(self, category, keyword, post_elements, city_url):
        existing_posts = self.get_existing_posts()
        new_posts = self.extract_posts(post_elements, keyword)

        for post in new_posts:
            # Check if the title already exists in the existing posts
            if any(
                existing_title == post["title"]
                for existing_title in existing_posts.values()
            ):
                self.app.log(f"Duplicate post found and skipped: {post['title']}")
            else:
                # Add the post to Google Sheets
                self.google_sheet.append_row(
                    [
                        self.country,
                        post["city"],
                        city_url,
                        category,
                        keyword,
                        post["title"],
                        post["url"],
                    ]
                )
                # Add the post to the CSV
                with open("output.csv", mode="a", newline="", encoding="utf-8") as file:
                    writer = csv.writer(file)
                    writer.writerow(
                        [
                            self.country,
                            post["city"],
                            city_url,
                            category,
                            keyword,
                            post["title"],
                            post["url"],
                        ]
                    )
                existing_posts[post["url"]] = post["title"]
                self.app.log(f"Post found and saved: {post['title']}")

    def get_existing_posts(self):
        return {
            row["Link"]: row["Post_title"]
            for row in self.google_sheet.get_all_records()
        }

    def extract_posts(self, post_elements, keyword):
        posts = []
        for element in post_elements:
            # Get the title and URL
            title = element.css(".title::text").get()
            url = element.css("a::attr(href)").get()

            # Check if both title and URL are found
            if title and url:
                title = title.strip()
                # Check if the keyword is in the title
                if keyword.lower() in title.lower():
                    posts.append({"title": title, "url": url})
            else:
                # Log if title or URL is missing
                if not title:
                    self.app.log("Warning: Post title element not found, skipping.")
                if not url:
                    self.app.log("Warning: Post URL element not found, skipping.")

        return posts


if __name__ == "__main__":
    root = tk.Tk()
    app = CraigslistScraperApp(root)
    root.mainloop()

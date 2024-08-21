# Selenium with pagination working fine and fetching all records

import time
import requests
import gspread
import csv
from oauth2client.service_account import ServiceAccountCredentials
from google.oauth2.service_account import Credentials
from scrapy.selector import Selector
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


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

        # Open and read the input CSV file
        with open("input.csv", "r", encoding="utf-8") as input_file:
            reader = csv.reader(input_file)

            for category, keyword in reader:
                print(f"Scraping Category: {category}")

                # Attempt to get the category page URL
                category_page_url_unfiltered = self.get_category_page_url(
                    resp, category, city_url
                )

                # Check if the category page URL was found
                if category_page_url_unfiltered:
                    # Update the category URL if needed
                    category_page_url = self.update_category_url(
                        category_page_url_unfiltered
                    )

                    # Proceed to scrape the posts if a valid category page URL is found
                    if category_page_url:
                        print(f"Scraped Category URL: {category_page_url}")
                        self.scrape_posts_selenium(
                            category, keyword, category_page_url, city_url
                        )
                else:
                    # Category page URL not found, skip this category
                    print(f"Skipping category '{category}' due to missing page.")
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
            print(f"Category page not found for '{category}' moving on to next city...")
            return False

        return category_page_url

    def update_category_url(self, url):
        # Parse the URL
        parsed_url = urlparse(url)

        # Extract the fragment
        fragment = parsed_url.fragment

        # Define the new search query
        new_search_query = "1~thumb~0~0"

        # Check if the URL contains '#search'
        if "#search" in url:
            # Split the fragment part into key-value pairs
            fragment_parts = fragment.split("=", 1)

            if len(fragment_parts) > 1:
                # Check if 'thumb' is in the query
                if "thumb" not in fragment_parts[1]:
                    # Replace the query after '#search'
                    updated_fragment = f"search={new_search_query}"
                else:
                    # Keep the fragment as is
                    updated_fragment = fragment
            else:
                # No key-value pair after '=', just replace with new query
                updated_fragment = f"search={new_search_query}"
        else:
            # Add '#search=1~thumb~0~0' if not present
            updated_fragment = f"search={new_search_query}"

        # Construct the new URL
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
                # Wait until posts are loaded
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
                    f"Number of posts fetched in page: {page_num+1} are: {num_results}"
                )

                if post_elements:
                    self.process_posts(category, keyword, post_elements, city_url)
                else:
                    print(
                        f"No posts found for keyword '{keyword}' in category '{category}'"
                    )

                # Check for the pagination element
                paginator = driver.find_element(
                    By.CSS_SELECTOR, "div.cl-search-paginator"
                )
                next_button = paginator.find_element(
                    By.CSS_SELECTOR, "button.bd-button.cl-next-page"
                )

                # If the "Next" button is disabled, break the loop
                if "bd-disabled" in next_button.get_attribute("class"):
                    print("No more pages to load. Going to next city...")
                    break

                # Click the "Next" button to load the next page
                next_button.click()
                page_num += 1

                # Wait for the next set of results to load
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "li.cl-search-result")
                    )
                )

        except Exception as e:
            print("An error occurred while scraping the category page:", e)

        finally:
            driver.quit()

    def process_posts(self, category, keyword, post_elements, city_url):
        existing_posts = self.get_existing_posts()

        for element in post_elements:
            try:
                # Safely locate the title element and get its text
                try:
                    title_element = element.find_element(
                        By.CSS_SELECTOR, "div.result-node a.posting-title span.label"
                    )
                    title = title_element.text.strip()
                except Exception as e:
                    print(f"Title not found: {e}")
                    continue

                # print(title)

                # Safely locate the URL element and get the href attribute
                try:
                    url_element = element.find_element(
                        By.CSS_SELECTOR, "div.result-node a.posting-title"
                    )
                    url = url_element.get_attribute("href")
                except Exception as e:
                    print(f"URL not found: {e}")
                    continue

                # Safely locate the date/time element and get the title attribute (datetime)
                try:
                    date_time_element = element.find_element(
                        By.CSS_SELECTOR, "div.result-node div.meta span[title]"
                    )
                    date_time = date_time_element.get_attribute("title").strip()
                except Exception as e:
                    print(f"Date/Time not found: {e}")
                    continue

                # Check if the keyword is in the title and if the post is not already saved
                if keyword.lower() in title.lower():
                    if url not in existing_posts:
                        # Add post to Google Sheet
                        self.add_post_to_google_sheet(
                            city_url,
                            category,
                            keyword,
                            {"title": title, "url": url, "date_time": date_time},
                        )
                        existing_posts[url] = title
                        print(f"Post added: {title}")
                    else:
                        print(f"Duplicate post found and skipped: {title}")

            except Exception as e:
                print(f"Error processing post: {e}")

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
            post.get("date_time", ""),
        ]
        self.google_sheet.append_row(row)
        print(f"Added post to Google Sheet: {post['title']}")


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

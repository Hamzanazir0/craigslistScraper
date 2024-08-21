import requests
import os
import csv
from scrapy.selector import Selector
from bs4 import BeautifulSoup
import re


class Craigslist:
    file_path = "Data.csv"
    country = "Canada"
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
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

    def target_url(self, ul):
        n = 0
        while n < 3:
            response = requests.get(
                ul,
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
            print()
            response = requests.get(
                str(city).strip(),
                headers=self.headers,
            )
            city_count = city_count + 1
            self.catagories(response, city)

    def catagories(self, response, city):
        resp = Selector(text=response.content)
        ul = response.url
        print()

        with open("input.csv", "r", encoding="utf-8") as input_file:
            reader = csv.reader(input_file, delimiter=",")
            for i in reader:
                catagory = str(i[0])
                keyword = str(i[1])
                keyword_xpath = "//a[contains(@data-alltitle,'" + catagory + "')]/@href"
                keyword_page = resp.xpath(keyword_xpath).extract_first()
                print()
                print("Currently Scraping Catagory", catagory)

                if not keyword_page or "#" in str(keyword_page).strip():
                    keyword_xpath = (
                        "//a[contains(@data-alltitle,'"
                        + str(catagory).strip().lower()
                        + "')]/@href"
                    )
                    keyword_page = resp.xpath(keyword_xpath).extract_first()
                if "https:" not in keyword_page:
                    keyword_page = re.sub(r"^\/", "", str(keyword_page))
                    keyword_page = str(ul) + str(keyword_page).strip()
                print("Scraped Catagory", keyword_page)
                response = requests.get(
                    str(keyword_page).strip(),
                    headers=self.headers,
                )
                self.scrap(catagory, keyword, response, city)

    def scrap(self, catagory, keyword, response, city):
        if not self.check_csv_file_exist():
            self.create_csv_file()
            self.add_urls(catagory, keyword, response, city)
        else:
            print("File already exist")
            self.check_current_urls_exist_in_csv(catagory, keyword, response, city)

    def check_current_urls_exist_in_csv(self, category, keyword, response, city):
        resp = Selector(text=response.content)
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
        resp = Selector(text=response.content)
        # soup = BeautifulSoup(response.content, 'html.parser')
        # print(soup.prettify())
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
                city_link = None
        else:
            city_link = None
        with open(self.file_path, "a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(
                [self.country, city_link, city, category, keyword, post_title, link]
            )


if __name__ == "__main__":
    scraper = Craigslist()
    urls = [
        "https://www.craigslist.org/about/sites#CA",
        "https://www.craigslist.org/about/sites#USA",
    ]
    for ul in urls:
        scraper.target_url(ul)

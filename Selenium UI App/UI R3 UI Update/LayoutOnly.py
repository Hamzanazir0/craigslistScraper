import sys
import os
import requests
import gspread
import threading
from PySide6.QtCore import Qt, QThread, Signal
from oauth2client.service_account import ServiceAccountCredentials
from scrapy.selector import Selector
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urlparse, urlunparse
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QComboBox,
    QLabel,
    QHBoxLayout,
    QCheckBox,
    QGridLayout,
    QTextEdit,
)


class CraigslistScraperUI(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Craigslist Scraper")
        self.resize(800, 600)

        # Country Selection
        self.country_label = QLabel("Select Country:")
        self.country_dropdown = QComboBox(self)
        self.country_dropdown.addItem("US")
        self.country_dropdown.addItem("Canada")
        self.country_dropdown.addItem("Canada & US")
        self.country_dropdown.currentIndexChanged.connect(self.on_country_change)

        # State/Province Selection
        self.state_label = QLabel("Select State/Province:")
        self.state_search_input = QLineEdit(self)
        self.state_search_input.setPlaceholderText("Search states/provinces...")

        self.canadian_state_list = QListWidget(self)
        self.canadian_state_list.setSelectionMode(QListWidget.MultiSelection)
        self.us_state_list = QListWidget(self)
        self.us_state_list.setSelectionMode(QListWidget.MultiSelection)

        self.select_all_states_checkbox = QCheckBox("Select All States/Provinces", self)
        self.select_all_states_checkbox.stateChanged.connect(
            self.toggle_select_all_states
        )

        state_layout = QGridLayout()
        state_layout.addWidget(QLabel("Canadian Provinces"), 0, 0)
        state_layout.addWidget(QLabel("US States"), 0, 1)
        state_layout.addWidget(self.canadian_state_list, 1, 0)
        state_layout.addWidget(self.us_state_list, 1, 1)

        # City Selection
        self.city_label = QLabel("Select City:")
        self.city_search_input = QLineEdit(self)
        self.city_search_input.setPlaceholderText("Search cities...")

        self.canadian_city_list = QListWidget(self)
        self.canadian_city_list.setSelectionMode(QListWidget.MultiSelection)
        self.us_city_list = QListWidget(self)
        self.us_city_list.setSelectionMode(QListWidget.MultiSelection)

        self.select_all_cities_checkbox = QCheckBox("Select All Cities", self)
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
        # self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.on_start_button_click)
        self.stop_button = QPushButton("Stop Scraping", self)
        # self.stop_button.clicked.connect(self.on_stop_button_click)
        self.stop_button.setEnabled(False)

        form_button_layout = QGridLayout()
        form_button_layout.addWidget(self.start_button, 0, 0)
        form_button_layout.addWidget(self.stop_button, 0, 1)

        # Console Output and Button
        self.clear_console_button = QPushButton("Clear Console")
        # self.clear_console_button.clicked.connect(self.on_clear_console_click)
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
        formlayout.addWidget(self.select_all_states_checkbox)
        formlayout.addWidget(self.city_label)
        formlayout.addWidget(self.city_search_input)
        formlayout.addLayout(city_layout)
        formlayout.addWidget(self.select_all_cities_checkbox)
        formlayout.addLayout(input_layout)
        formlayout.addLayout(form_button_layout)

        self.setLayout(layout)

    def on_country_change(self):
        selected_country = self.country_dropdown.currentText()
        self.load_states(selected_country)

    def load_states(self, country):
        self.log_output.append(f"Loading States/Provinces of {country}")
        self.canadian_state_list.clear()
        self.us_state_list.clear()
        canadian_states = []
        us_states = []
        if country == "Canada" or country == "Canada & US":
            canadian_states = [
                "Ontario",
                "Quebec",
                "British Columbia",
            ]
        if country == "US" or country == "Canada & US":
            us_states = [
                "California",
                "New York",
                "Texas",
            ]
        for state in canadian_states:
            self.canadian_state_list.addItem(QListWidgetItem(state))
        for state in us_states:
            self.us_state_list.addItem(QListWidgetItem(state))
        self.log_output.append(f"Loading of States/Provinces completed.")

    def toggle_select_all_states(self, state):
        for i in range(self.canadian_state_list.count()):
            item = self.canadian_state_list.item(i)
            item.setSelected(state == 2)
        for i in range(self.us_state_list.count()):
            item = self.us_state_list.item(i)
            item.setSelected(state == 2)

    def toggle_select_all_cities(self, state):
        for i in range(self.canadian_city_list.count()):
            item = self.canadian_city_list.item(i)
            item.setSelected(state == 2)
        for i in range(self.us_city_list.count()):
            item = self.us_city_list.item(i)
            item.setSelected(state == 2)

    def on_start_button_click(self):
        selected_canadian_states = [
            item.text() for item in self.canadian_state_list.selectedItems()
        ]
        selected_us_states = [
            item.text() for item in self.us_state_list.selectedItems()
        ]
        selected_canadian_cities = [
            item.text() for item in self.canadian_city_list.selectedItems()
        ]
        selected_us_cities = [item.text() for item in self.us_city_list.selectedItems()]
        keyword = self.keyword_input.text()
        category = self.category_input.text()

        if not selected_canadian_states and not selected_us_states:
            print("Please select at least one state or province.")
            return
        if not selected_canadian_cities and not selected_us_cities:
            print("Please select at least one city.")
            return
        if not keyword or not category:
            print("Please fill all fields.")
            return

        print(
            "Scraping data for:",
            selected_canadian_states,
            selected_us_states,
            selected_canadian_cities,
            selected_us_cities,
            keyword,
            category,
        )
        # Trigger scraping logic here...


if __name__ == "__main__":
    app = QApplication([])

    window = CraigslistScraperUI()
    window.show()

    app.exec()

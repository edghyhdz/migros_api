import requests
import json
import re
import logging
import os
import sys
import time
import platform
from typing import Dict
from bs4 import BeautifulSoup as bs
from datetime import datetime,timedelta
import numpy as np
import pandas as pd
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .exceptions_migros import ExceptionMigrosApi
from .receipt_item import ReceiptItem

# Configure logging
FILE_PATH_CONF = "./"
FILE_NAME_CONF = "log_files.log"

logging.basicConfig(
    format='%(levelname)s: %(asctime)s - %(message)s [%(filename)s:%(lineno)s - %(funcName)s()]',
    datefmt='%d-%b-%y %H:%M:%S',
    level=logging.DEBUG,
    handlers=[
        logging.FileHandler(os.path.join(FILE_PATH_CONF, FILE_NAME_CONF)),
        logging.StreamHandler()
    ]
)

class MigrosApi:
    """Migros API class for interacting with Migros/Cumulus services"""

    def __init__(self, password: str, username: str):
        """Initialize MigrosApi with credentials"""
        self.__password = password
        self.__username = username
        self.__user_real_name = ""
        
        # Initialize session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        
        # Set up browser-like headers
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Sec-Ch-Ua": "\"Not_A Brand\";v=\"8\", \"Chromium\";v=\"120\", \"Google Chrome\";v=\"120\"",
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": "\"Windows\"",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        }
        
        # URLs
        self.csrf_pattern = r'(?<="_csrf" content=")([^"]+)'
        self.login_url = "https://login.migros.ch/login"
        self.cumulus_login = "https://www.migros.ch/de/cumulus/konto~checkImmediate=true~.html"
        self.url_receipts = "https://www.migros.ch/de/cumulus/konto/kassenbons.html?sort=dateDsc&dateFrom={0}&dateTo={1}"
        self.url_export_data = "https://www.migros.ch/service/avantaReceiptExport/"
        
        # Initialize session and login
        try:
            self._init_session()
            self._login_cumulus()
        except Exception as e:
            logging.error(f"Initialization failed: {str(e)}")
            raise

    @property
    def user_name(self) -> str:
        return self.__user_real_name
    
    @user_name.setter
    def user_name(self, user_name: str) -> None:
        self.__user_real_name = user_name
    
    @property
    def user_email(self) -> str:
        return self.__username

    def _format_date(self, date: datetime) -> str:
        """Format date in a platform-independent way"""
        day = str(date.day).zfill(2)
        month = str(date.month).zfill(2)
        return f"{date.year}-{month}-{day}"

    def _init_session(self):
        """Initialize session with main page visit"""
        try:
            main_page = "https://www.migros.ch/"
            logging.info("Initializing session with main page visit...")
            response = self.session.get(main_page, headers=self.headers)
            response.raise_for_status()
            time.sleep(1)
        except Exception as e:
            logging.error(f"Failed to initialize session: {str(e)}")
            raise

    def __authenticate(self):
        """Authenticate to the Migros website."""
        try:
            # Update headers for login page
            login_headers = self.headers.copy()
            login_headers.update({
                "Sec-Fetch-Site": "same-origin",
                "Referer": "https://www.migros.ch/"
            })
            
            logging.info("Fetching login page...")
            response = self.session.get(self.login_url, headers=login_headers, timeout=10)
            response.raise_for_status()
            time.sleep(1)

            # Extract CSRF token
            csrf_match = re.search(self.csrf_pattern, response.text)
            if not csrf_match:
                logging.error("CSRF token not found")
                raise ExceptionMigrosApi(1, "CSRF token not found")
            csrf_token = csrf_match.group(1)
            logging.info(f"CSRF token retrieved: {csrf_token[:5]}...")

            # Update headers for POST request
            post_headers = login_headers.copy()
            post_headers.update({
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://login.migros.ch",
                "Referer": self.login_url
            })

            # Prepare login payload
            payload = {
                "_csrf": csrf_token,
                "username": self.__username,
                "password": self.__password,
                "remember-me": "true"
            }

            time.sleep(2)

            # Submit login request
            logging.info("Submitting login request...")
            response = self.session.post(
                self.login_url, 
                headers=post_headers, 
                data=payload,
                allow_redirects=True,
                timeout=10
            )
            response.raise_for_status()

            # Check response
            soup = bs(response.text, "html.parser")
            error_messages = soup.find_all(class_=["error", "error-message", "alert-danger"])
            
            if error_messages:
                error_text = " | ".join([msg.get_text(strip=True) for msg in error_messages])
                raise ExceptionMigrosApi(1, f"Login failed: {error_text}")

            if "authentication_error" in response.url.lower():
                raise ExceptionMigrosApi(1, "Authentication failed")

            logging.info("Login successful.")
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Request failed during authentication: {str(e)}")
            raise ExceptionMigrosApi(1, f"Network error during authentication: {str(e)}")
        except ExceptionMigrosApi:
            raise
        except Exception as e:
            logging.error(f"Unexpected error during authentication: {str(e)}")
            raise ExceptionMigrosApi(1, f"Authentication failed: {str(e)}")

    def _login_cumulus(self):
        """Log in to the Cumulus account."""
        try:
            self.__authenticate()
            
            # Update cookies and headers for Cumulus
            self.headers['cookie'] = '; '.join([f"{x.name}={x.value}" for x in self.session.cookies])
            self.headers.update({
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                "accept-language": "en-US,en;q=0.9,de;q=0.8",
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "same-origin",
                "upgrade-insecure-requests": "1",
                "referer": "https://www.migros.ch/de"
            })

            logging.info("Logging into Cumulus account...")
            response = self.session.get(
                self.cumulus_login,
                headers=self.headers,
                params={
                    "referrer": "https://www.migros.ch/resources/loginPage~lang=de~.html",
                    "referrerPolicy": "no-referrer-when-downgrade"
                },
                allow_redirects=True
            )
            response.raise_for_status()
            
            # Verify Cumulus access
            soup = bs(response.text, "html.parser")
            cumulus_elements = soup.find_all(string=lambda text: "Cumulus" in str(text))
            
            if not cumulus_elements:
                raise ExceptionMigrosApi(3, "Failed to access Cumulus account")
                
            logging.info("Successfully accessed Cumulus account")
            
        except ExceptionMigrosApi:
            raise
        except Exception as e:
            logging.error(f"Unexpected error during Cumulus login: {str(e)}")
            raise ExceptionMigrosApi(3, f"Cumulus login failed: {str(e)}")

    def get_all_receipts(self, period_from: datetime, period_to: datetime, **kwargs) -> Dict[str, dict]:
        """Retrieves dictionary with receipt (kassenbons) ids as key and receipt information as values.
        Receipt information includes: receipt_id, store_name, cost, and cumulus_points
        
        Args:
            period_from (datetime): period from, to execute search
            period_to (datetime): period to, to execute search

        Returns:
            Dict[str, dict]: Period receipts information
        """
        current_page = 1
        response_list = []
        if "response" in kwargs:
            response_list = kwargs.get("response")

        try:
            # Validate dates
            for date in (period_from, period_to):
                if not isinstance(date, datetime):
                    raise ExceptionMigrosApi(4)
            if period_from > period_to:
                raise ExceptionMigrosApi(5)

            # Format dates using platform-independent method
            period_from_str = self._format_date(period_from)
            period_to_str = self._format_date(period_to)

            # Update headers
            self.headers['cookie'] = '; '.join([
                f"{k}={v}" for k, v in self.session.cookies.get_dict().items()
            ])
            self.headers.update({
                "accept": "text/html, */*; q=0.01",
                "accept-language": "de",
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "x-requested-with": "XMLHttpRequest"
            })

            # Request parameters
            params = {
                "referrer": "https://www.migros.ch/de/cumulus/konto/kassenbons.html",
                "referrerPolicy": "no-referrer-when-downgrade"
            }

            # Build request URL and get receipts
            request_url = self.url_receipts.format(period_from_str, period_to_str)
            final_dict = {}

            while True:
                url = f"{request_url}&p={current_page}"
                response = self.session.get(url, headers=self.headers, params=params)
                response_list.append(response)

                total_pages = self._parse_receipt_data(response, final_dict)
                
                if current_page >= total_pages:
                    break
                    
                current_page += 1
                time.sleep(1)  # Add delay between pages

            return final_dict

        except ExceptionMigrosApi as e:
            logging.error(f"API error in get_all_receipts: {str(e)}")
            raise
        except Exception as err:
            error_line = sys.exc_info()[-1].tb_lineno
            logging.error(f"Unhandled error in get_all_receipts: {str(err)}, line: {error_line}")
            raise Exception(f"Failed to get receipts: {str(err)}")

    def get_receipt(self, receipt_id: str) -> ReceiptItem:
        """Retrieves receipt from given receipt_id and returns it as a ReceiptItem object.
        Contains items bought information, with quantities and prices.

        Args:
            receipt_id (str): receipt id to get data

        Returns:
            ReceiptItem: Object containing receipt bought items information
        """
        try:
            # Build up cookies and headers
            self.headers['cookie'] = '; '.join([
                f"{k}={v}" for k, v in self.session.cookies.get_dict().items()
            ])
            self.headers.update({
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                "sec-fetch-dest": "iframe",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "same-origin",
                "sec-fetch-user": "?1",
                "upgrade-insecure-requests": "1",
                "referrer": "https://www.migros.ch/de/cumulus/konto/kassenbons.html"
            })

            params = {
                "referrer": "https://www.migros.ch/de/cumulus/konto/kassenbons.html",
                "referrerPolicy": "no-referrer-when-downgrade"
            }

            # Build URLs
            request_url = f"{self.url_export_data}html?receiptId={receipt_id}"
            request_pdf = f"{self.url_export_data}pdf?receiptId={receipt_id}"
            
            logging.debug("Fetching receipt from: %s", request_url)

            # Get both HTML and PDF versions
            response = self.session.get(request_url, headers=self.headers, params=params)
            response_pdf = self.session.get(request_pdf, headers=self.headers, params=params)

            response.raise_for_status()
            response_pdf.raise_for_status()

            # Clean receipt ID
            receipt_id = receipt_id.split("?")[0]

            return ReceiptItem(
                receipt_id=receipt_id,
                soup=response.content,
                pdf=response_pdf.content
            )

        except requests.exceptions.RequestException as e:
            logging.error(f"Network error getting receipt {receipt_id}: {str(e)}")
            raise ExceptionMigrosApi(f"Failed to retrieve receipt {receipt_id}")
        except Exception as err:
            error_line = sys.exc_info()[-1].tb_lineno
            logging.error(f"Error getting receipt {receipt_id}: {str(err)}, line: {error_line}")
            raise ExceptionMigrosApi(f"Failed to process receipt {receipt_id}: {str(err)}")

    def _parse_receipt_data(self, response: bytes, result_dict: dict) -> int:
        """Parses response data to a dictionary. Helper function for get_all_receipts method.

        Args:
            response (bytes): requests response
            result_dict (dict): dictionary to update items into

        Returns:
            int: total number of pages of items from requested time period
        """
        try: 
            # Parse response content
            soup = bs(response.content, 'lxml')

            # Get pagination information
            pages = []
            for item in soup.find_all('a', attrs={"aria-label": "Seite"}):
                page_value = item.get('data-value')
                if page_value and page_value.isnumeric():
                    pages.append(int(page_value))
            
            total_pages = max(pages) if pages else 1

            # Parse receipt items
            for item in soup.find_all('input', attrs={'type': 'checkbox'}): 
                # Skip the "select all" checkbox
                if item.get('value') == 'all':
                    continue

                download_id = item.get('value')
                
                # Find related elements
                pdf_ref = item.find_next('a', attrs={'class': 'ui-js-toggle-modal'})
                if not pdf_ref:
                    logging.warning(f"No PDF reference found for item {download_id}")
                    continue

                receipt_id = pdf_ref.get('href').split("receiptId=")[-1]
                
                # Get receipt details
                store_name = pdf_ref.find_next('td')
                cost = store_name.find_next('td') if store_name else None
                points = cost.find_next('td') if cost else None

                if not all([store_name, cost, points]):
                    logging.warning(f"Missing data for receipt {receipt_id}")
                    continue

                # Store receipt information
                result_dict[download_id] = {
                    'pdf_ref': pdf_ref.get('href'),
                    'receipt_id': receipt_id,
                    'store_name': store_name.text.strip(),
                    'cost': cost.text.strip(),
                    'cumulus_points': points.text.strip()
                }

            return total_pages

        except Exception as err:
            error_line = sys.exc_info()[-1].tb_lineno
            logging.error(f"Error parsing receipt data: {str(err)}, line: {error_line}")
            raise Exception(f"Failed to parse receipt data: {str(err)}")
        



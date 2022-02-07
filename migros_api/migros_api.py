"""migros_api class"""

import requests
import json
import re
import logging
import os
import sys
from typing import Dict
from bs4 import BeautifulSoup as bs
from datetime import datetime
import numpy as np
import pandas as pd
from .exceptions_migros import ExceptionMigrosApi
from .receipt_item import ReceiptItem


FILE_PATH_CONF = "./"
FILE_NAME_CONF = "log_files.log"

logging.basicConfig(
    format='%(levelname)s: %(asctime)s - %(message)s [%(filename)s:%(lineno)s - %(funcName)s()]',
    datefmt='%d-%b-%y %H:%M:%S',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(os.path.join(FILE_PATH_CONF, FILE_NAME_CONF)),
        logging.StreamHandler()
    ]
)


class MigrosApi: 
    """ Migros api class declaration and definition """

    def __init__(self, password, username):


        self.__password = password
        self.__username = username
        self.__user_real_name = ""

        self.session = requests.session()
        self.headers = {}

        self.csfr_pattern = r'(?<="_csrf" content=)(.*)(?=\/>)'
        self.login_url = "https://login.migros.ch/login"
        self.cumulus_login = "https://www.migros.ch/de/cumulus/konto~checkImmediate=true~.html"
        self.url_receipts = "https://www.migros.ch/de/cumulus/konto/kassenbons.html?sort=dateDsc&dateFrom={0}&dateTo={1}"
        self.url_export_data = "https://www.migros.ch/service/avantaReceiptExport/"

        # Log into cumulus
        self._login_cumulus()
        
    # ---------------------------------------------------------------------------------------------
    # Typical behavioral methods ------------------------------------------------------------------
    @property
    def user_name(self) -> str:
        return self.__user_real_name
    
    @user_name.setter
    def user_name(self, user_name: str) -> None:
        self.__user_real_name = user_name
    
    @property
    def user_email(self) -> str:
        return self.__username
    
    # ---------------------------------------------------------------------------------------------
    # Private methods -----------------------------------------------------------------------------

    def __authenticate(self):
        """ Initial authentication to migros.ch/login using 
            username and password

        Raises:
            ExceptionMigrosApi: In case username was not found on migros site, meaning 
                that authentication has failed
            Exception: If credentials do not match any user on migros side
        """

        try: 
            self.headers = {
                'accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                "accept-language": "en-US,en;q=0.9",
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "same-origin",
                'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'
            }

            logging.debug("Getting CSRF token")
            response = self.session.get(self.login_url, headers=self.headers)

            # Build up cookies
            self.headers['cookie'] = '; '.join([x.name + '=' + x.value for x in response.cookies])
            self.headers['content-type'] = 'application/x-www-form-urlencoded'

            # Search first for the CSRF token upon first get request
            csrf = re.search(self.csfr_pattern, response.text).group(0)
            csrf = eval(csrf)
            display_token = csrf[0:5] + "...."
            logging.debug("Found CSR token: %s", display_token)

            # Build up authentication payload
            raw_data = "_csrf={0}&username={1}&password={2}".format(csrf, self.__username, self.__password)
            
            # Authenticate
            response = self.session.post(self.login_url, headers=self.headers, data=raw_data)
            response.raise_for_status()
            status_code = response.status_code

            logging.debug("Response: %s", status_code)

            soup = bs(response.content, 'lxml')

            # Check if we have logged in successfully
            soup_item = soup.find("div", attrs={"class": "m-accountmenu"})

            if not soup_item:
                raise ExceptionMigrosApi(1)

            # If the following attribute is true, then we are pretty much in
            if soup_item.get('data-logged-in') != 'true':
                raise ExceptionMigrosApi(1)

            email_address = soup_item.find(
                "span", attrs={"class": "m-accountmenuflyout__info-mail"}
            ).text

            # If email address not found
            if email_address != self.user_email:
                raise ExceptionMigrosApi(2)
            
            # Get user name
            self.user_name = soup_item.find(
                "span", attrs={"class": "m-accountmenuflyout__info-title"}
            ).text
        
        except Exception as err:
            error_line = sys.exc_info()[-1].tb_lineno
            raise Exception("Unhandled exception, line: %s" % error_line)

    def _login_cumulus(self):
        """ After initially login into migros, Cumulus requires an extra get request to land 
            into the cumulus site

        Raises:
            ExceptionMigrosApi: In case username was not found on cumulus site, meaning 
                that authentication has failed
            Exception: Unhandled exceptions
        """

        try: 
            self.__authenticate()

            # Update cookies
            self.headers['cookie'] = '; '.join([x.name + '=' + x.value for x in self.session.cookies])

            # Update headers
            self.headers.update(
                {
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                    "accept-language": "en-US,en;q=0.9",
                    "sec-fetch-dest": "document",
                    "sec-fetch-mode": "navigate",
                    "sec-fetch-site": "same-origin",
                    "upgrade-insecure-requests": "1",
                }
            )

            params = {
                "referrer": "https://www.migros.ch/resources/loginPage~lang=de~.html",
                "referrerPolicy": "no-referrer-when-downgrade",
            }

            logging.debug("Login into cumulus account")
            response = self.session.get(self.cumulus_login, headers=self.headers, params=params)
            status_code = response.status_code
            logging.debug("Status code: %s", status_code)
                
        except Exception as err:
            error_line = sys.exc_info()[-1].tb_lineno
            raise Exception("Unhandled exception, line: %s" % error_line)
    
    # ---------------------------------------------------------------------------------------------
    # Public methods ------------------------------------------------------------------------------

    def get_all_receipts(self, period_from: datetime, period_to: datetime, **kwargs) -> Dict[str, dict]:
        """ Retrieves dictionary with receipt (kassenbons) ids as key and receipt information as values.
            Receipt information includes the following, 
                `receipt_id`, `store_name`, `cost`, and `cumulus_points`
            
        Args:
            period_from (datetime): period from, to execute search
            period_to (datetime): period to, to execute search

        Raises:
            ExceptionMigrosApi: if `period_from` or `period_to` are not datetime objects
            ExceptionMigrosApi: if `period_from` > `period_to`
            Exception: for any other unhandled exceptions

        Returns:
            Dict[str, dict]: Period receipts information
        """

        current_page = 1

        # Used for troubleshooting, store response inside a list
        response_list = []
        if "response" in kwargs:
            response_list = kwargs.get("response")
        try:
            # Check that all dates provided are correctly formatted
            for date in (period_from, period_to): 
                if not isinstance(period_from, datetime): 
                    raise ExceptionMigrosApi(4)

            if period_from > period_to:
                raise ExceptionMigrosApi(5)

            # Format according to payload needs
            period_from = datetime.strftime(period_from, "%Y-%m-%-d")
            period_to = datetime.strftime(period_to, "%Y-%m-%-d")

            # Build up cookies -> otherwise it will not work
            self.headers['cookie'] = '; '.join(
                [
                    x[0] + '=' + x[1] for x in self.session.cookies.get_dict().items()
                ]
            )

            self.headers.update(
                {
                    "accept": "text/html, */*; q=0.01",
                    "accept-language": "de",
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-origin",
                    "x-requested-with": "XMLHttpRequest",
                }
            )

            params = {
                "referrer": "https://www.migros.ch/de/cumulus/konto/kassenbons.html",
                "referrerPolicy": "no-referrer-when-downgrade",
            }

            # Request url to get receipts
            request_url = self.url_receipts.format(period_from, period_to)

            # While we have pages available on cumulus side keep on getting the data
            final_dict = {}

            url = request_url + "&p=%s" % current_page
            response = self.session.get(url, headers=self.headers, params=params)

            # For troubleshooting purposes
            response_list.append(response)

            # First response will give us info on how many pages to expect
            total_pages: int = self._parse_receipt_data(response, final_dict)

            # Keep on getting item data until we ran out of pages
            while current_page != total_pages:
                current_page += 1
                url = request_url + "&p=%s" % current_page
                response = self.session.get(url, headers=self.headers, params=params)
                response_list.append(response)

                total_pages: int = self._parse_receipt_data(response, final_dict)
            
            return final_dict

        except Exception as err:
            error_line = sys.exc_info()[-1].tb_lineno
            raise Exception("Unhandled exception error: %s, line: %s" % (err, error_line))

    def get_receipt(self, receipt_id: str) -> ReceiptItem:
        """ Retrieves receipt from given `receipt_id` and returns it into
            a `ReceiptItem` object. Object contains items bought 
            information, with quantities and prices

        Args:
            receipt_id (str): receipt id to get data

        Returns:
            ReceiptItem: Object containing receipt bought items information
        """

        # Build up cookies -> otherwise it will not work
        self.headers['cookie'] = '; '.join(
            [
                x[0] + '=' + x[1] for x in self.session.cookies.get_dict().items()
            ]
        )
        self.headers.update(
            {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "sec-fetch-dest": "iframe",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "https://www.migros.ch/de/cumulus/konto/kassenbons.html",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "referrer": "https://www.migros.ch/de/cumulus/konto/kassenbons.html",
            "referrerPolicy": "no-referrer-when-downgrade",
            }
        )

        # Check if parameters are indeed needed
        params = {
            "referrer": "https://www.migros.ch/de/cumulus/konto/kassenbons.html",
            "referrerPolicy": "no-referrer-when-downgrade"
        }

        # Build url to search on that given period
        request_url = self.url_export_data + "%s?receiptId=%s" % ('html', receipt_id)
        logging.debug("Export url: %s", request_url)

        request_pdf = self.url_export_data + "%s?receiptId=%s" % ('pdf', receipt_id)

        response = self.session.get(request_url, headers=self.headers, params=params)
        response_pdf = self.session.get(request_pdf, headers=self.headers, params=params)

        receipt_id = receipt_id.split("?")[0]

        return ReceiptItem(receipt_id=receipt_id, soup=response.content, pdf=response_pdf.content)
    
    # ---------------------------------------------------------------------------------------------
    # Helper functions ----------------------------------------------------------------------------

    def _parse_receipt_data(self, response: bytes, result_dict: dict) -> int:
        """ Parses response data to a dictionary. Used as a helper function to 
            the get_all_receipts() method

        Args:
            response (bytes): requests response
            result_dict (dict): dictionary to update items into

        Raises:
            Exception: For unhandled exceptions

        Returns:
            int: total number of pages of items from requested time period
        """
        try: 
            # Get total number of pages
            soup = bs(response.content, 'lxml')

            pages = []
            for item in soup.find_all('a', attrs={"aria-label": "Seite"}):
                page_value = item.get('data-value')
                if page_value.isnumeric():
                    page_value = int(page_value)
                    pages.append(page_value)
            
            total_pages = 1
            if pages:
                # Gets total number of pages from query
                total_pages = np.max(pages)

            for item in soup.find_all('input', attrs={'type': 'checkbox'}): 
                # Don't take first checkbox item to select all tick boxes
                if 'all' not in item.get('value'):
                    download_id = item.get('value')
                    pdf_ref = item.find_next('a', attrs={'class': 'ui-js-toggle-modal'})
                    recepit_id = pdf_ref.get('href').split("receiptId=")[-1]
                    store_name = pdf_ref.find_next('td')
                    cost = store_name.find_next('td')
                    points = cost.find_next('td')

                    # TODO: Better formatting of results
                    result_dict[download_id] = {
                        'pdf_ref': pdf_ref.get('href'),
                        'receipt_id': recepit_id,
                        'store_name': store_name.text,
                        'cost': cost.text,
                        'cumulus_points': points.text
                    }

            return total_pages

        except Exception as err:
            error_line = sys.exc_info()[-1].tb_lineno
            raise Exception("Unhandled exception error: %s, line: %s" % (err, error_line))


if __name__ == "__main__":
    from getpass import getpass

    PWD = os.environ['PASSWORD_MIGROS']
    USERNAME = os.environ['USERNAME_MIGROS']

    if not PWD:
        PWD = getpass("GIVE ME YOUR PSWORD: ")
    if not USERNAME:
        USERNAME = input("GIVE ME YOUR USERNAME: ")

    MIGROS_API = MigrosApi(username=USERNAME, password=PWD)
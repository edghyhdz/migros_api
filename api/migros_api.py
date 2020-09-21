"""migros_api class"""

import requests
import json
import re
import logging
import os
import sys
from bs4 import BeautifulSoup as bs
from datetime import datetime
import numpy as np
import pandas as pd


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

# TODO: 
# Get it into pdf format? 
# Add decorators for user required
# Add exception class
# Check which headers are trully required or not
# Check which params are also required in requests
# Use regex to search for username


class MigrosApi(object): 
    """Migros api, inherits from config file all methods"""

    def __init__(self, password, username):
        super(MigrosApi, self).__init__()

        self.session = requests.session()
        self.headers = {}
        self.login_url = "https://login.migros.ch/login"
        self.password = password
        self.username = username
        self.csfr_pattern = r'(?<="_csrf" content=)(.*)(?=\/>)'
        self.cumulus_login = "https://www.migros.ch/de/cumulus/konto~checkImmediate=true~.html"
        self.url_kassenbons = "https://www.migros.ch/de/cumulus/konto/kassenbons/variants/variant-1/content/04/ajaxContent/0.html?period="
        self.url_export_data = "https://www.migros.ch/service/avantaReceiptExport/"
        self.user_real_name = ""
        self.total_pages = 0
        self.page_counter = 1
        self.resulting_cumulus_dict = {}
        self.period_from: datetime = datetime.now()
        self.period_to: datetime = datetime.now()

        # Log into cumulus
        self.login_cumulus()

    def authenticate(self):
        """authenticate with init credentials
        """

        try: 
            self.headers = {
                'accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'
            }

            logging.info("Getting CSRF token")
            response = self.session.get(self.login_url, headers=self.headers)

            # Build up cookies
            self.headers['cookie'] = '; '.join([x.name + '=' + x.value for x in response.cookies])
            self.headers['content-type'] = 'application/x-www-form-urlencoded'

            
            csrf = re.search(self.csfr_pattern, response.text).group(0)
            csrf = eval(csrf)
            display_token = csrf[0:5] + "...."
            logging.info("Found CSR token: %s", display_token)
            raw_data = "_csrf={0}&username={1}&password={2}".format(csrf, self.username, self.password)
            
            # Authenticate
            response = self.session.post(self.login_url, headers=self.headers, data=raw_data)
            response.raise_for_status()
            status_code = response.status_code

            logging.info("Response: %s", status_code)

            soup = bs(response.content, 'lxml')

            script = soup.find(
                'script', attrs={
                    "data-t-name": "DataLayerInit"
                }
            )

            if not script:
                raise ExceptionMigrosApi(1)
            else: 
                soup_item = soup.find('li', attrs={'class': 'o-header__name'})
                if soup_item:
                    self.user_real_name = soup_item.text
                    logging.info("Logged in succesfully: %s", self.user_real_name)           
                else:
                    raise ExceptionMigrosApi(2)     

        except ExceptionMigrosApi as err:
            error_line = sys.exc_info()[-1].tb_lineno
            logging.error("%s, error line: %s", *(err.error_codes[err.code], error_line))
        
        except Exception as err:
            error_line = sys.exc_info()[-1].tb_lineno
            logging.error("Error when authenticating: %s, line: %s", *(err, error_line))

    def login_cumulus(self):
        """log into cumulus
        """

        try: 
            self.authenticate()

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

            logging.info("Login into cumulus account")
            response = self.session.get(self.cumulus_login, headers=self.headers, params=params)
            status_code = response.status_code
            logging.info("Status code: %s", status_code)

            matches = re.findall(r'{}'.format(self.user_real_name), response.text)
            if matches:
                logging.info("Logged in successfully to cumulus")
            else:
                raise ExceptionMigrosApi(3)
        
        except ExceptionMigrosApi as err:
            error_line = sys.exc_info()[-1].tb_lineno
            logging.error("%s, error line: %s", *(err.error_codes[err.msg], error_line))
        
        except Exception as err:
            error_line = sys.exc_info()[-1].tb_lineno
            logging.error("Error when authenticating: %s, line: %s", *(err, error_line))

    def get_all_kasenbons(self, period_from: datetime, period_to: datetime, all_pages=False, **kwargs):
        """
        Retrieves all kasenbons ids, with their respective date/place of the event
        
        Args:
            period_from (datetime): from which date do search
            period_to (datetime): to which date extend the search
            all_pages (boolean): default <False>, whether to fetch all data from 
            all resulting pages or not
        """

        # To be used to query next page with results
        self.period_from = period_from
        self.period_to = period_to

        # To identify when it was sent by 
        get_next_page = False
        for key in kwargs:
            if 'get_next_page' in key:
                get_next_page = kwargs['get_next_page']
                
        try: 
            for date in (period_from, period_to): 
                if not isinstance(period_from, datetime): 
                    raise ExceptionMigrosApi(4)
            
            period_from = datetime.strftime(period_from, "%Y-%m-%-d")
            period_to = datetime.strftime(period_to, "%Y-%m-%-d")

            # Build up cookies -> otherwise it will not work
            self.headers['cookie'] = '; '.join(
                [
                    x[0] + '=' + x[1] for x in self.session.cookies.get_dict().items()
                ]
            )

            # Build url to search on that given period
            request_url = self.url_kassenbons + "%s_%s" % (period_from, period_to)
            if get_next_page:
                logging.info("Should be getting next page")
                request_url = request_url + "&p%s" % self.page_counter
                logging.info("URL NEW: %s", request_url)

            request_url = request_url.strip()
            logging.info("request url: %s", request_url)
            
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

            response = self.session.get(request_url, headers=self.headers, params=params)
            # It seems that always the status code is 200, even if user is not
            # authenticated
            status_code = response.status_code
            logging.info("Status code kassenbons: %s", status_code)

            result_dictionary = self.parse_kassenbon_data(response=response)

            return result_dictionary

        except ExceptionMigrosApi as err:
            error_line = sys.exc_info()[-1].tb_lineno
            logging.error("%s, error line: %s", *(err.error_codes[err.msg], error_line))

        except Exception as err:
            error_line = sys.exc_info()[-1].tb_lineno
            logging.error("Error: %s, line: %s", *(err, error_line))
    
    def parse_kassenbon_data(self, response: bytes):
        """
        Parses bit data to a dictionary. Used as a helper function to 
        the get_all_kasenbons() method

        Args:
            response (bytes): requests.content
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
            # Gets total number of pages from query
            self.total_pages = np.max(pages)

            # Counts which page are we in
            self.page_counter += 1

            logging.info("Total of pages for this query: %s", self.total_pages)

            self.resulting_cumulus_dict = {}

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
                    self.resulting_cumulus_dict[download_id] = {
                        'pdf_ref': pdf_ref.get('href'),
                        'receipt_id': recepit_id,
                        'store_name': store_name.text,
                        'cost': cost.text,
                        'cumulus_points': points.text
                    }

            return self.resulting_cumulus_dict, response.content

        # TODO: Error handling for this method
        except ExceptionMigrosApi as err:
            error_line = sys.exc_info()[-1].tb_lineno
            logging.error("%s, error line: %s", *(err.error_codes[err.msg], error_line))

        except Exception as err:
            error_line = sys.exc_info()[-1].tb_lineno
            logging.error("Error: %s, line: %s", *(err, error_line))
    
    def get_next_kassenbons_page(self): 
        """
        If user does not select get all
        """
        if self.page_counter <= self.total_pages:
            result_dict = self.get_all_kasenbons(self.period_from, self.period_to, get_next_page=True)
            return result_dict
        else:
            #TODO: review this result
            # in case of error then also go back one page in case of line 267 max np
            # error handling for that case
            # 
            logging.info("No more pages to query")

    def get_kassenbon(self, receipt_id: str, export_type: str):
        """
        Fetches specified receipt from id

        Args:
            receipt_id (str): id from receipt
            export_type (str): type to export, accepted <html> and <pdf>

        Returns:
            [bytes]: returns requested file
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
        request_url = self.url_export_data + "%s?receiptId=%s" % (export_type, receipt_id)
        logging.info("Export url: %s", request_url)

        response = self.session.get(request_url, headers=self.headers, params=params)

        return ReceiptItem(response.content)


# TODO: Handle errors for this class
class ReceiptItem:
    """
    Receipt items to be parsed as df or as bytes
    """

    def __init__(self, soup: bytes):
        super(ReceiptItem).__init__()
        self.soup = bs(soup, 'lxml')
        self.index_to_ignore = set()

    def get_raw_data(self) -> bytes:
        """
        get soup
        """
        return self.soup

    def get_data_frame(self) -> pd.DataFrame:
        """
        Returns:
            pd.DataFrame: [description]
        """
        df_result = self.parse_receipt_data()
        return df_result

    def parse_receipt_data(self):
        """
        Only german -> todo french and italian
        """

        data_text = self.soup.find('div', attrs={'class': 'article pre'}).text
        data_text.split("\n")
        
        for k, txt in enumerate(data_text.split("\n")):
            if 'CHF' in txt:
                self.index_to_ignore = set()
                df_result = self.receipt_data_parser_type_one(data_text)
                break
            else:
                df_result = self.receipt_data_parser_type_two(data_text)
                break
        return df_result

    def receipt_data_parser_type_one(self, data_text: str):
        """
        Two types of receipts
        """
        new_text = []
        
        for k, txt in enumerate(data_text.split("\n")):
            if (txt != "") & ('CHF' not in txt):
                temp_list = [x.strip() for x in txt.split("  ") if x!= ""]
                if 'AKT' not in temp_list:
                    temp_list.insert(0, ' ')
                new_text.append(temp_list)
                
        df_temp_data = pd.DataFrame(new_text)
        
        frame = []
        for df_type in ['AKT', 'SEVERAL', '']:
            df_bdf = self.build_data_frame(df_data=df_temp_data, df_type=df_type)
            frame.append(df_bdf)
        df_final = pd.concat(frame, sort=False)
        df_final = df_final.reset_index().drop(columns='index')
        
        return df_final

    def receipt_data_parser_type_two(self, data_text: str):
        """
        Two types of receipts
        """
        # There are two types of receipts -> limmatfeld

        new_text = []

        for k, txt in enumerate(data_text.split("\n")):
            if txt:
                if k==0:
                    col_names = [x.strip() for x in txt.split("  ") if x!= ""]
                else:     
                    temp = [x.strip() for x in txt.split("  ") if x!= ""]
                    new_text.append(temp)

        if len(temp) == 5:
            idx_pop = col_names.index('Gespart')
            col_names.pop(idx_pop)
            
        df_receipt = pd.DataFrame(new_text, columns=col_names)
        df_receipt['Gespart'] = ['' for x in df_receipt.Menge]
        df_receipt = df_receipt[['Artikelbezeichnung', 'Menge', 'Preis', 'Gespart', 'Total']]
        
        return df_receipt
    
    def build_data_frame(self, df_data: pd.DataFrame, df_type: str):
        """
        Used by receipt_data_parser_type_one() method
        to build three different types of data frames

        """
        
        if df_type == 'SEVERAL': 
            temp_df = df_data[(df_data[3].isna()) & (df_data[0] != 'AKT')]
            index_quantity = temp_df.index
            
        elif df_type == 'AKT':
            temp_df = df_data[(df_data[3].isna()) & (df_data[0] == 'AKT')]
            index_quantity = temp_df.index
            
        else: 
            index_to_ignore_list = list(self.index_to_ignore)
            temp_df = df_data[(df_data[3].isna() == False) & (df_data.index.isin(index_to_ignore_list) == False)]
        
        if df_type in ['SEVERAL', 'AKT']:
            
            new_data = []
            for idx in index_quantity:
                new_index = idx + 1
                
                self.index_to_ignore.add(new_index)

                if df_type == 'AKT': 
                    akt_index = idx + 2
                    self.index_to_ignore.add(akt_index)
                    df_aktien = df_data[df_data.index == akt_index]
                    # Aktien part
                    akt_price = df_aktien[2].values[0]
                    akt_price = akt_price.replace("-", '')
                    akt_price = float(akt_price) * -1
                else:
                    akt_price = 0
                    
                df_current = df_data[df_data.index == idx]
                df_temp = df_data[df_data.index == new_index]
                
                menge, price = df_temp[1].values[0].split("x")
                total = df_temp[2].values[0]
                if "-" in total:
                    total = total.replace("-", "")
                    total = float(total) * -1
                else:
                    total = float(total)
                menge = float(menge.strip())
                price = float(price.strip())

                concept = df_current[1].values[0]

                new_data.append((concept, menge, price, akt_price, total))

            columns = ['Artikelbezeichnung', 'Menge', 'Preis', 'Gespart', 'Total']
            
            df_final = pd.DataFrame(new_data, columns=columns)  
            df_final["Total"] = df_final['Total'] + df_final['Gespart']
        else:
            df_final = temp_df.rename(columns={0: 'Gespart', 1: 'Artikelbezeichnung', 2: 'Preis', 3: 'Menge'}).reset_index()
            df_final = df_final.drop(columns='index')
            df_final['Gespart'] = [0 for x in df_final['Preis']]
            df_final['Preis'] = [float(x) for x in df_final['Preis']]
            df_final['Total'] = df_final['Preis']
            
        return df_final


class ExceptionMigrosApi(Exception):
    """
    Handles all exceptions related to MigrosAPI Class
    """
    error_codes = {
        '1': "Could not authenticate",
        '2': "Could not find username when authenticating", 
        '3': "Could not authenticate to cumulus",
        '4': "period_from and period_to should be datetime objects"
    }

    def __init__(self, code):
        self.code = code
        self.msg = str(code)



if __name__ == "__main__":
    from getpass import getpass
    # PWD = os.environ.get("PASSWORD_MIGROS")
    # USERNAME = os.environ.get("USERNAME_MIGROS")
    PWD = None
    USERNAME = None

    if not PWD:
        PWD = getpass("GIVE ME YOUR PSWORD: ")
        os.environ['PASSWORD_MIGROS'] = PWD
    if not USERNAME:
        USERNAME = input("GIVE ME YOUR USERNAME: ")
        os.environ['USERNAME_MIGROS'] = USERNAME

    MIGROS_API = MigrosApi(username=USERNAME, password=PWD)
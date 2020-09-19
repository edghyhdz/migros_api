"""migros_api class"""

import requests
import json
import re
import logging
import os
import sys
from bs4 import BeautifulSoup as bs
from datetime import datetime


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
# Provide get_kassenbons result in a list or dictionary format
# Fetch specific kasenbon with id
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
                    user_name = soup_item.text
                    logging.info("Logged in succesfully: %s", user_name)           
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

            matches = re.findall(r'{}'.format("test"), response.text)
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

    def get_all_kasenbons(self, period_from: datetime, period_to: datetime):
        """
        Retrieves all kasenbons ids, with their respective date/place of the event
        
        Args:
            period_from (datetime): from which date do search
            period_to (datetime): to which date extend the search
        """

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

            # # First call kassenbons main site to get new cookies
            # url_test = 'https://www.migros.ch/de/cumulus/konto/kassenbons.html'
            # response = self.session.get(url_test, headers=self.headers)
            # response_code = response.status_code
            # logging.info("Response code for main kassenbons site: %s", response_code)

            # return response.text

            # Build url to search on that given period
            request_url = self.url_kassenbons + "%s_%s" % (period_from, period_to)
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
            logging.info(response.text)

            return response.text

        except ExceptionMigrosApi as err:
            error_line = sys.exc_info()[-1].tb_lineno
            logging.error("%s, error line: %s", *(err.error_codes[err.msg], error_line))

        except Exception as err:
            error_line = sys.exc_info()[-1].tb_lineno
            logging.error("Error: %s, line: %s", *(err, error_line))

    def get_kassenbon(self, k_id: str):
        """
        Gets specific kassenbon
        Args:
            k_id (str): kassenbon to retrieve given a kassenbon id
        """
        pass
    

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

import os
import logging
from bs4 import BeautifulSoup as bs
import pandas as pd
import sys
from .exceptions_migros import ExceptionMigrosApi


class ReceiptItem:
    """
    Receipt items to be parsed as data frame or as bytes
    """
    def __init__(self, receipt_id: str, soup: bytes, pdf=None):
        self._receipt_id = receipt_id
        self._soup = bs(soup, 'lxml')
        self._pdf = pdf
        self._index_to_ignore = set()

    def get_raw_data(self) -> bytes:
        """ Get raw soup in bytes of the receipt item that was queried

        Returns:
            bytes: Beautifoulsoup object
        """
        return self._soup

    def get_data_frame(self) -> pd.DataFrame:
        """ Parses all purchase data into a pandas data frame

        Returns:
            pd.DataFrame: All `receipt_id` purchase data as a data frame
        """

        return self._parse_receipt_data()
    
    def to_pdf(self, path: str) -> None:
        """
        Uses response that parses bytes to generate pdf

        Args: 
            path (str): path where to save pdf
        """
        try: 
            if self._pdf:
                file_name = self._receipt_id + ".pdf"
                full_path = os.path.join(path, file_name)
                with open(full_path, 'wb') as file:
                    file.write(self._pdf)
                logging.debug("Saved file: %s", file_name)
            else:
                raise ExceptionMigrosApi(6)

        except Exception as err:
            line_no = sys.exc_info()[-1].tb_lineno
            raise Exception("Unhandled exception, error: %s, line: %s" % (err, line_no))

    def _parse_receipt_data(self):
        """
        Parses bytes content into data frame from queried bytes receipt item
        """
        try: 
            data_text = self._soup.find('div', attrs={'class': 'article pre'}).text
            data_text.split("\n")
            
            for k, txt in enumerate(data_text.split("\n")):
                if 'CHF' in txt:
                    self._index_to_ignore = set()
                    df_result = self._receipt_data_parser_type_one(data_text)
                    break
                else:
                    df_result = self._receipt_data_parser_type_two(data_text)
                    break

            return df_result

        except Exception as err:
            error_line = sys.exc_info()[-1].tb_lineno
            logging.error("Unknown error: %s, line: %s", *(err, error_line))

    def _receipt_data_parser_type_one(self, data_text: str):
        """
        Helper function to `_parse_receipt_data()` method

        Migros uses two types of receipts, depending on which type we are dealing with
        we use one of these two methods to parse byte data into data frame
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
            df_bdf = self._build_data_frame(df_data=df_temp_data, df_type=df_type)
            frame.append(df_bdf)
        df_final = pd.concat(frame, sort=False)
        df_final = df_final.reset_index().drop(columns='index')
        
        return df_final

    def _receipt_data_parser_type_two(self, data_text: str):
        """
        Helper function to _parse_receipt_data() method
        
        Migros uses two types of receipts, depending on which type we are dealing with
        we use one of these two methods to parse byte data into data frame
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
        
        for row in new_text:
            if len(row) == 5:
                row.insert(3, '')
            
        df_receipt = pd.DataFrame(new_text, columns=col_names)
        df_receipt['Gespart'] = ['' for x in df_receipt.Menge]
        df_receipt = df_receipt[['Artikelbezeichnung', 'Menge', 'Preis', 'Gespart', 'Total']]
        
        return df_receipt
    
    def _build_data_frame(self, df_data: pd.DataFrame, df_type: str):
        """
        Used by `_receipt_data_parser_type_one()` method
        to build three different types of data frames
        """

        # Depending on the row type
        if df_type == 'SEVERAL': 
            temp_df = df_data[(df_data[3].isna()) & (df_data[0] != 'AKT')]
            index_quantity = temp_df.index
            
        elif df_type == 'AKT':
            temp_df = df_data[(df_data[3].isna()) & (df_data[0] == 'AKT')]
            index_quantity = temp_df.index
            
        else: 
            index_to_ignore_list = list(self._index_to_ignore)
            temp_df = df_data[(df_data[3].isna() == False) & (df_data.index.isin(index_to_ignore_list) == False)]
        
        if df_type in ['SEVERAL', 'AKT']:
            
            new_data = []
            for idx in index_quantity:
                new_index = idx + 1
                
                self._index_to_ignore.add(new_index)

                if df_type == 'AKT': 
                    akt_index = idx + 2
                    self._index_to_ignore.add(akt_index)
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
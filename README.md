<h1 align="left">
  <br>
  <a><img src="https://abs.twimg.com/emoji/v2/svg/1f603.svg" alt="Markdownify" width="200"></a>
  <br>Unofficial Migros API
  <br>
</h1>

<h4 align="left">An unofficial Migros API (more like Cumulus API) to fetch cumulus and receipt data, as well as receipt PDFs!</h4>

## Description
This script uses python requests to authenticate to the official Migros website. Once authenticated via password and username, you can further authenticate with your cumulus account.

You can see a brief showcase of how it can be used either on the video below, or in the description that follows. 

![screenshot](https://github.com/edghyhdz/migros_api/blob/master/usage.gif)

## Usage
1. `git clone` this repository
2. Once inside the root directory where you cloned this repo,

```python
from api.migros_api import MigrosApi
from datetime import datetime, timedelta
from getpass import getpass

pwd = getpass("yourpassword": )
email = "youremail@email.com"  # Username of your migros account

migros_api = MigrosApi(pwd, email)

```

3. Once authenticated, it will let you know whether it was successful or not
  - If it was successful, then you can proceed to authenticate to your cumulus account like so
 ```python
migros_api.login_cumulus()
```
  - Where if successful, you should see the loggin message stating so.
  
4. Once authenticated, you can use the following methods,
```python
migros_api.get_all_kasenbons(period_from: datetime, period_to: datetime)
```
 - This method will get all receipts from a given period of time, indicated by the `period_from` and `period_to` parameters
 - This will return a tuple, containing a dictionary with all requested receipts, plus the raw data
 5. You can retrieve a specific receipt with the method `get_kassenbon()` like so, 
 ```python
receipt = migros_api.get_kassenbon(receipt_id: str)
type(receipt) -> ReceiptItem
```
 - This will return a ReceiptItem, that itself has the following methods,
  ```python
receipt.get_raw_data()  
```
 - Gets all raw data from requested receipt
 
```python
receipt.get_data_frame()  
```
 - Parses receipt data into dataframe
 
```python
receipt.to_pdf(path: str)  
```
 - Saving receipt as pdf to the given `path` folder


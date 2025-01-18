"""Migros API Exception Classes"""

class ExceptionMigrosApi(Exception):
    """Custom exception class for Migros API errors"""
    
    ERROR_CODES = {
        # Authentication errors
        1: "Could not authenticate",
        '1': "Could not authenticate",
        2: "Could not find username when authenticating",
        '2': "Could not find username when authenticating",
        3: "Could not authenticate to cumulus",
        '3': "Could not authenticate to cumulus",
        
        # Parameter validation errors
        4: "period_from and period_to should be datetime objects",
        '4': "period_from and period_to should be datetime objects",
        5: "`period_from` should be <= to `period_to`",
        '5': "`period_from` should be <= to `period_to`",
        
        # Request errors
        6: "Request again the item and indicate request_pdf=True",
        '6': "Request again the item and indicate request_pdf=True"
    }
    
    def __init__(self, code=None, message=None):
        # Convert code to string for consistency
        self.code = str(code) if code is not None else None
        
        # Use custom message if provided, otherwise look up in ERROR_CODES
        if message is not None:
            self.msg = message
        elif self.code is not None:
            self.msg = self.ERROR_CODES.get(self.code) or self.ERROR_CODES.get(int(self.code))
        else:
            self.msg = "Unknown error occurred"
            
        super().__init__(self.msg)
    
    def __str__(self):
        if self.code:
            return f"Error {self.code}: {self.msg}"
        return self.msg
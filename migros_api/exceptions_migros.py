class ExceptionMigrosApi(Exception):
    """
    Handles all exceptions related to MigrosAPI Class
    """

    def __init__(self, code):
        error_codes = {
            '1': "Could not authenticate",
            '2': "Could not find username when authenticating", 
            '3': "Could not authenticate to cumulus",
            '4': "period_from and period_to should be datetime objects",
            '5': "`period_from` should be <= to `period_to`",
            '6': "Request again the item and indicate request_pdf=True"
        }
        self.code = str(code)
        self.msg = error_codes.get(code)
    
    def __str__(self):
        return self.msg

        

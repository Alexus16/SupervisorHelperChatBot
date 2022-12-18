# Simple telegram bot for collecting student attendence statistic
## Files content in DATA_PATH directory
### Credentials - credentials.json
This file includes only 1 necessary field:
'token' - bot access token
### Current day data - group_data.json
This file contains data for correct bot restart
### Saved reports - reports/ *(directory)*
This directory contains .txt files containing saved data

## Startup
To proper bot start you should:
1. Specify DATA_PATH in main.py
2. Put your access token to field 'token' in credentials.json located in DATA_PATH
3. start bot (ex. from console by python main.py)

### Warning: bad code!

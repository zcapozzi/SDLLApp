# -*- coding: utf-8 -*-
"""
Created on Tue Nov 17 14:10:05 2015

@author: zcapozzi002
"""

import time, datetime, sys, os, random, math
from time import strptime
from datetime import datetime, date, timedelta
import traceback, telepot
from collections import defaultdict

import MySQLdb, subprocess

ALERTS = {}

SITE_MAROON = (128, 0, 0)
SITE_BLUE = (24, 154, 211)
SITE_PURPLE = (132, 68, 238)
SITE_RED = (128, 0, 0)
SITE_GREEN = (67, 143, 77)

import requests
import json

import re

piFolder = "/home/pi/zack/"
if not os.path.isdir(piFolder):
    piFolder = "C:\\Users\\zcapo\\Documents\\workspace"
    if not os.path.isdir(piFolder):
        piFolder = "C:\\Users\\zcapozzi002\\Documents\\workspace"

zc_fldr = os.path.join(piFolder,"ZackInc")
sdll_fldr = os.path.join(piFolder,"SDLL")
lr_fldr = os.path.join(piFolder,"LacrosseReference")
mlb_fldr = os.path.join(piFolder, "MLB", "Newsletter")
magick_path = os.path.join(piFolder, "ImageMagick", "magick.exe")

sys.path.insert(0, lr_fldr)
import laxref
sys.path.insert(0, zc_fldr)
import zack_inc_lite as zc


bot_token = json.loads(open(os.path.join(sdll_fldr, "client_secrets.json"), 'r').read())['local']['bot_token']
image_bot_token = json.loads(open(os.path.join(sdll_fldr, "client_secrets.json"), 'r').read())['local']['image_bot_token']



from apiclient import discovery
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage
from oauth2client import service_account
from oauth2client.service_account import ServiceAccountCredentials
import googleapiclient.errors
import httplib2
from oauth2client import client
from oauth2client import file
from oauth2client import tools

def read_from_google_sheet(tag, misc, specs):
    """
    This function allows this script to read from the budget Google sheet
    https://docs.google.com/spreadsheets/d/1wpVRlXrjDoVcaaYUsjwHPkdrTN1i9mr-aN7Ijav2-UM/edit?gid=0#gid=0
    """
    
    print ("Googling...")
    
    #SCOPES = 'https://www.googleapis.com/auth/spreadsheets'
    #CLIENT_SECRET_FILE = 'client_secret.json'
    #APPLICATION_NAME = 'Other client 12'

    #credentials = ServiceAccountCredentials.from_json_keyfile_name(os.path.join(sdll_fldr,'sdll-466220-c134386b092d.json'), [SCOPES])
    #http = credentials.authorize(httplib2.Http())

    #discoveryUrl = ('https://sheets.googleapis.com/$discovery/rest?' 'version=v4')
    #service = discovery.build('sheets', 'v4', http=http, discoveryServiceUrl=discoveryUrl)
    service = zc.get_SDLL_sheets_API_service_object()

    spreadsheetId = None
    if IS_SPRING and datetime.now().year==2025:
        spreadsheetId = '1OmVS-RR-JazRRwGD7IEL7fmzHqWScTSgpFavMsJdbsc'
    if not IS_SPRING and datetime.now().year==2025:
        spreadsheetId = '1Zh82z1Grwfw679TAvRgE7f4Ctmmxj2kYUX1KnhoiHp0'
    if IS_SPRING and datetime.now().year==2026:
        spreadsheetId = '1lKL-0Owd52EkLBANaB_27nOOh4sii3yDKkYzFI7JcrY'
    misc['spreadsheetId'] = spreadsheetId
    if misc.get('spreadsheetId') is None and '--show-assignr-counts-by-umpires' not in sys.argv:
        erro_msg = "[SDLL FAIL]\n\nNo master schedule sheet ID found; likely this is because the sheet ID is not available for the current season"
        laxref.telegram_alert(erro_msg + "\n\n" + zc.get_original_script_command())
        zc.exit("FAIL")
        
    def col_to_char(i):
            if i+1 <= 26:
                return "%s" % (chr(64+ i + 1))
            elif i+1 <= 52:
                return "%s" % (chr(64+ i - 26 + 1))
    if tag == "umpireFeedback":    
        for division in specs['divisions']:
            if '-division' in sys.argv and sys.argv[sys.argv.index('-division') + 1] != division['alt_name']:
                continue
            division['sheets'] = []
            
            spreadsheet = service.spreadsheets().get(spreadsheetId=division['sheet_id']).execute()
            sheets = spreadsheet.get('sheets', [])

            # Loop through each sheet
            n_sheets = len(sheets)
            print("")
            for ij, sheet in enumerate(sheets):
                
                sheet_title = sheet['properties']['title']
                if sheet_title.startswith("Sheet"): continue
                print(f"Reading {division['league']} sheet ({ij+1}/{n_sheets}): {sheet_title}")
                d = {'title': sheet_title}
                if sheet_title not in ['STANDINGS']:
                    values = service.spreadsheets().values().get(spreadsheetId=division['sheet_id'], range=f"'{sheet_title}'!A1:AZ100", valueRenderOption='UNFORMATTED_VALUE').execute(); time.sleep(.5)
                    d['raw_values'] = values['values']
                    division['sheets'].append(d)
    elif tag == "all_games_master_doc":
    
        values = service.spreadsheets().values().get(spreadsheetId=spreadsheetId, range="Master!A1:T9999", valueRenderOption='UNFORMATTED_VALUE').execute()
        misc['master_sheet_raw_values'] = values['values']
        
        # Identify the column that contains the database IDs that match the records on the Sheets to the records in SDLL_Games
        misc['matching_db_ID_column'] = None
        misc['matching_db_ID_range'] = None
        misc['column_locs'] = {}
        misc['column_chars'] = {}
        misc['sheet_db_IDs_array'] = [[""] for z in range(len(misc['master_sheet_raw_values']) - 1)]

                
        for i, val in enumerate(misc['master_sheet_raw_values'][0]):
            if val == "Umpire Matching ID - DO NOT UPDATE":
                misc['matching_db_ID_column'] = i; 
                if i+1 <= 26:
                    misc['matching_db_ID_range'] = "%s2:%s%d" % (chr(64+ i + 1), chr(64+ i + 1), len(misc['master_sheet_raw_values']))
                elif i+1 <= 52:
                    misc['matching_db_ID_range'] = "%s2:%s%d" % (chr(64+ i - 26 + 1), chr(64+ i - 26 + 1), len(misc['master_sheet_raw_values']))
                break
        
            if val == "Cancelled":
                misc['column_locs']['cancelled'] = i
                misc['column_chars']['cancelled'] = col_to_char(i)
            if val == "Activity":
                misc['column_locs']['game_type'] = i
                misc['column_chars']['game_type'] = col_to_char(i)
                
            
    elif tag in ["vanceSheet", "martiSheet"]:
    
        if tag == "martiSheet":
            values = service.spreadsheets().values().get(spreadsheetId=spreadsheetId, range="Marti - Umpire!A1:T9999", valueRenderOption='UNFORMATTED_VALUE').execute()
        if tag == "vanceSheet":
            values = service.spreadsheets().values().get(spreadsheetId=spreadsheetId, range="Vance - Umpire!A1:T9999", valueRenderOption='UNFORMATTED_VALUE').execute()
        misc['master_sheet_raw_values'] = values['values']
        
        # Identify the column that contains the database IDs that match the records on the Sheets to the records in SDLL_Games
        misc['matching_db_ID_column'] = None
        misc['matching_db_ID_range'] = None
        misc['column_locs'] = {}
        misc['column_chars'] = {}
        misc['sheet_db_IDs_array'] = [[""] for z in range(len(misc['master_sheet_raw_values']) - 1)]

                
        for i, val in enumerate(misc['master_sheet_raw_values'][0]):
            if val == "Umpire Matching ID - DO NOT UPDATE":
                misc['matching_db_ID_column'] = i; 
                if i+1 <= 26:
                    misc['matching_db_ID_range'] = "%s2:%s%d" % (chr(64+ i + 1), chr(64+ i + 1), len(misc['master_sheet_raw_values']))
                elif i+1 <= 52:
                    misc['matching_db_ID_range'] = "%s2:%s%d" % (chr(64+ i - 26 + 1), chr(64+ i - 26 + 1), len(misc['master_sheet_raw_values']))
                break
        
            if val == "Cancelled":
                misc['column_locs']['cancelled'] = i
                misc['column_chars']['cancelled'] = col_to_char(i)
            if val == "Activity":
                misc['column_locs']['game_type'] = i
                misc['column_chars']['game_type'] = col_to_char(i)
                
            
        
    elif tag == "teamKey":
    
        values = service.spreadsheets().values().get(spreadsheetId=spreadsheetId, range="Team Key!A2:L9999", valueRenderOption='UNFORMATTED_VALUE').execute()
        misc['team_key_sheet_raw_values'] = values['values']
        
        # Identify the column that contains the database IDs that match the records on the Sheets to the records in SDLL_Games
        misc['coaches_by_team_display_name'] = defaultdict(list)
        email_regex = re.compile(r'([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63})(?:[\s,;\n\r><\]]|$)', re.IGNORECASE)        
        rows_with_email = {}
        headers = {}; header_row = None
        for i, row in enumerate(misc['team_key_sheet_raw_values']):
            for val in row:
                if header_row is None and val in ["Division", "Team Code", "Team Name", "Head Coach"]:
                    header_row = i
                match = email_regex.search(val)
                if match:
                    team = "%s - %s" % (row[1].strip(), row[2].strip())
                    if 0 and "Pink Panthers" in team:
                        print (team + "|")
                        print (row)
                        print (match.group(1))
                        print (misc['coaches_by_team_display_name'][team])
                        zc.exit("PNTHS")
                        
                    if match.group(1) not in misc['coaches_by_team_display_name'][team]:
                        misc['coaches_by_team_display_name'][team].append(match.group(1))
                        rows_with_email.update({i: 1})
        
        misc['coaches_by_team'] = defaultdict(list)
        misc['coaches_last_name_lookup'] = {}
        
        email_regex = re.compile(r'([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63})(?:[\s,;\n\r><\]]|$)', re.IGNORECASE)        
        for i, row in enumerate(misc['team_key_sheet_raw_values']):
            d = {'head_coach_name': None, 'head_coach_email': None, 'has_email': 0}
            if len(row) > 2:
                team = "%s - %s" % (row[1].strip(), row[2].strip())
                if i == header_row:
                    for j, val in enumerate(row):
                        headers[j] = val
                if rows_with_email.get(i) is not None:
                    #print (row)
                    league = row[0]
                    last_name_league_tup = None
                    if not league.startswith("SB ") and "BB " not in league:
                        league = "BB {}".format(league)
                    for j, val in enumerate(row):
                        #print ("{:<10}{}".format(j, val))
                        if len(headers) > j and  headers[j] in ['Head Coach']:
                            d['head_coach_name'] = val
                            hardCodedLastNames = {}
                            hardCodedLastNames['James Van Strander'] = "Van Strander"
                            hardCodedLastNames['Matthew Van Jura'] = "Van Jura"
                            
                            tokens = val.strip().split(" ")
                            hard_code = hardCodedLastNames.get(val.strip())
                            d['head_coach_last_name'] = None
                            if hard_code is not None:
                                d['head_coach_last_name'] = hard_code
                            elif len(tokens) == 2:
                                d['head_coach_last_name'] = tokens[-1]
                            else:
                                tmp_msg = "[SDLL WARNING]\n\nNeed to hard-code the last name for %s" % (val)
                                print (tmp_msg)
                                laxref.telegram_alert(tmp_msg)
                           
                            last_name_league_tup = (league, d['head_coach_last_name'])
                            
                        if len(headers) > j and  headers[j] in ['Head Coach Email']:
                            d['head_coach_email'] = val
                            d['has_email'] = 1
                    misc['coaches_by_team'][team].append(d)
                    misc['coaches_last_name_lookup'].update({last_name_league_tup: team})
    return misc, service

def send_email(msg, specs = {}):
    
    if 'to' in specs and specs['to'] in ['admin', '[admin]']:
        # Replace the placeholder text with the admin email address
        specs['to'] = json.loads(open(os.path.join(sdll_fldr, "client_secrets.json"), 'r').read())['local']['admin_email']
        
    if '-quiet' not in sys.argv and 'quiet' not in sys.argv:
        if 'subject' not in specs: specs['subject'] = "Email from Script"
        tokens = open(os.path.join(piFolder, 'gmc+SDLL'), 'r').read().strip().split("\n")
        password = tokens[0]
        to = tokens[1]
        
        app_password = None
        if len(tokens) > 2:
            app_password = tokens[2]
        username = to
        
        import smtplib
        server = smtplib.SMTP('smtp.gmail.com:587'); 
        server.ehlo(); 
        server.starttls()
        server.ehlo(); 
        try:

            server.login(username, password)
            print ("Password worked...")
        except:
            #print (traceback.format_exc())
            server.login(username, app_password)
            print ("App Password worked...")
        
        if 'from' not in specs:
            specs['from'] = username
        if 'to' in specs:
            to = specs['to']
        dt_str = datetime.now().strftime("%H:%M %Y-%m-%d")
        if 'subject' not in specs:
            specs['subject'] = "TELEGRAM {}".format(dt_str)

        if isinstance(to, list):
            to_header = ", ".join(to)   # For email header
            to_addrs = to               # For server.sendmail
        else:
            to_header = to
            to_addrs = [to]

        # Use to_header for msg headers
        #email_msg['To'] = to_header
        final_content = None
        if "<html" in msg.lower() or "</html>" in msg.lower():
            from email.mime.multipart import MIMEMultipart
            from email.mime.application import MIMEApplication
            from email.mime.text import MIMEText
            from os.path import basename
            email_msg = MIMEMultipart('alternative')
            email_msg['Subject'] = specs['subject']
            email_msg['From'] = username
            email_msg['To'] = to_header
            part1 = MIMEText("", 'plain', 'utf-8')
            part2 = MIMEText(msg, 'html', 'utf-8')
            email_msg.attach(part1)
            email_msg.attach(part2)
            
            if 'attachments' in specs and specs['attachments'] is not None:
                files_to_attach = [specs['attachments']] if isinstance(specs['attachments'], str) else specs['attachments']
                for f in files_to_attach:
                    with open(f, "rb") as fil:
                        part = MIMEApplication(
                            fil.read(),
                            Name=basename(f)
                        )
                    # After the file is closed
                    part['Content-Disposition'] = 'attachment; filename="%s"' % basename(f)
                    print("Attach the attachment")
                    email_msg.attach(part)
            #server.sendmail(username, to, email_msg.as_string())
            final_content = email_msg.as_string()
        else:
            if specs.get('attachments') is not None:
                from email.mime.multipart import MIMEMultipart
                from email.mime.application import MIMEApplication
                from email.mime.text import MIMEText
                from os.path import basename
                email_msg = MIMEMultipart('alternative')
                email_msg['Subject'] = specs['subject']
                email_msg['From'] = specs['from']
                email_msg['To'] = to_header
                part1 = MIMEText(msg, 'plain', 'utf-8')
                email_msg.attach(part1)
                
            
                files_to_attach = [specs['attachments']] if isinstance(specs['attachments'], str) else specs['attachments']
                for f in files_to_attach:
                    with open(f, "rb") as fil:
                        part = MIMEApplication(
                            fil.read(),
                            Name=basename(f)
                        )
                    # After the file is closed
                    part['Content-Disposition'] = 'attachment; filename="%s"' % basename(f)
                    print("Attach the attachment")
                    email_msg.attach(part)
                #server.sendmail(username, to, email_msg.as_string())
                final_content = email_msg.as_string()
            else:
                
                #msg = ("Subject: {}\r\nFrom: {}\r\nTo: {}\r\n\r\n{}" .format (specs['subject'], specs['from'], t, msg))
                msg = ("Subject: {}\r\nFrom: {}\r\nTo: {}\r\n\r\n{}" .format (specs['subject'], specs['from'], to_header, msg))
                
                final_content = msg
            
            #server.sendmail(username, to, msg)
        #server.sendmail(username, to, final_content.encode('utf-8'))
        server.sendmail(username, to_addrs, final_content.encode('utf-8'))
            
            
        server.quit()
        
    
def clean_league_name(s, fn_specs={}):
    """
    Handles some common spelling mistakes with respect to league
    """
    if datetime.now() > datetime(2026, 8, 1):
        laxref.telegram_alert("[SDLL]\n\nConfirm that the league cleaning rules are still accurate.\n\nEspecially, are we still assuming that non-labeled leagues are Baseball?")
        zc.exit("CONFIRM THAT THESE ARE STILL ACCURATE!!!")
    if "Rookies" in s: s = s.replace("Rookies", "Rookie")
    if s == "A": s = "BB A"
    if s == "AA": s = "BB AA"
    if s == "AAA": s = "BB AAA"
    if s == "Grapefruit": s = "BB AAA"
    if s == "Cactus": s = "BB AA"
    if s == "Intermediate": s = "BB Intermediate"
    if s == "UMP": s = "BB A"
    if s == "Rookie": s = "BB Rookie"
    if s == "LMP": s = "BB Rookie"
    if s == "Majors": s = "BB Majors"
    if s == "Juniors": s = "BB Juniors"
    if s == "Tee Ball": s = "BB Tee Ball"
    return s

def is_TBD(team, fn_specs={}):
    res = 0
    hashed_name = laxref.hash_player_name(team)
    if hashed_name.endswith("tbd"):
        res = 1
    return res
    
def clean_team_name(s, fn_specs={}):
    """
    Handles some common spelling mistakes with respect to team_name
    """
    if isinstance(s, str):
        if "Rookies" in s: s = s.replace("Rookies", "Rookie")
        
    return s
    
def convert_master_sheet_data_to_games(misc, service, fn_specs):
    
    if 'alternate_names' not in misc:
        cursor = zc.zcursor("SDLL")
        misc['alternate_names'] = cursor.dqr("SELECT a.ID, a.team_ID, a.alternate_name, b.display_name actual_name from SDLL_Alternate_Team_Names a, SDLL_Team_Seasons b where b.is_spring=%s and b.active and a.team_ID=b.team_ID and a.year=b.year and a.active and a.year=%s;", [IS_SPRING, datetime.now().year])
        cursor.close()
    
    if fn_specs['version'] == 1:
        misc['doc_games'] = []
        misc['sheet_db_ID_data'] = []
        for i in range(len(misc['master_sheet_raw_values'])):
            d = {'source_row': i+1, 'game_date': None, 'end_date': None, 'duration_in_hours': None, 'home_team': None, 'away_team': None, 'league': None, 'location': None, 'notes': None, 'game_type': '', 'status': None, 'db_game_ID': None}
            tmp_end_time = None
            # Support vars
            
            row_n_cols = len(misc['master_sheet_raw_values'][i])
            
            #print ("\n #%d (%d cols)" % (i+1, row_n_cols))
            #print(misc['master_sheet_raw_values'][i])
            try:
                d['game_date'] = (datetime(1900, 1, 1)+timedelta(days=misc['master_sheet_raw_values'][i][1]-2))
                
            except Exception:
                pass # Not a date  

            if d['game_date'] is not None:
                start_time_identified = 0
                try:
                    midnight = datetime.combine(d['game_date'], datetime.min.time())
                    time_value = midnight + timedelta(hours=misc['master_sheet_raw_values'][i][3]*24.)
                    d['game_date'] = time_value
                    
                    start_time_identified = 1
                except Exception:
                    pass # Not a date    
                
                if len(misc['master_sheet_raw_values'][i]) > 4 and misc['master_sheet_raw_values'][i][4] not in ['', None, 'None']:
                    try:
                        midnight = datetime.combine(d['game_date'], datetime.min.time())
                        #print ("")
                        #print (midnight)
                        #print (misc['master_sheet_raw_values'][i][4])
                        #print (misc['master_sheet_raw_values'][i][4]*24.)
                        
                        time_value = midnight + timedelta(hours=misc['master_sheet_raw_values'][i][4]*24.)
                        tmp_end_time = time_value
                        if start_time_identified:
                            d['duration_in_hours'] = (tmp_end_time - d['game_date']).total_seconds() / 3600
                            d['end_date'] = d['game_date'] + timedelta(seconds=d['duration_in_hours'] * 3600.)
                    except Exception:
                        zc.exit(traceback.format_exc()) 
                    
            d['db_game_ID'] = None if row_n_cols <= 16 else clean_team_name(misc['master_sheet_raw_values'][i][16], {'row': misc['master_sheet_raw_values'][i]})
            d['home_team'] = None if row_n_cols <= 9 else clean_team_name(misc['master_sheet_raw_values'][i][9], {'row': misc['master_sheet_raw_values'][i]})
            d['away_team'] = None if row_n_cols <= 8 else clean_team_name(misc['master_sheet_raw_values'][i][8], {'row': misc['master_sheet_raw_values'][i]})
            
            # See if the names are actually alternate names for an existing team record
            team_no_space = laxref.hash_player_name(str(d['home_team']), {'keep_numbers': 1})
            if team_no_space in [laxref.hash_player_name(str(z['alternate_name']), {'keep_numbers': 1}) for z in misc['alternate_names']]:
                tmp_rec = misc['alternate_names'][ [laxref.hash_player_name(str(z['alternate_name']), {'keep_numbers': 1}) for z in misc['alternate_names']].index(team_no_space) ]
                msg = "It appears that {} actually maps to team ID {} ({})".format(d['home_team'], tmp_rec['team_ID'], tmp_rec['actual_name'])
                
                d['home_team'] = tmp_rec['actual_name']
            
            team_no_space = laxref.hash_player_name(str(d['away_team']), {'keep_numbers': 1})
            if team_no_space in [laxref.hash_player_name(str(z['alternate_name']), {'keep_numbers': 1}) for z in misc['alternate_names']]:
                tmp_rec = misc['alternate_names'][ [laxref.hash_player_name(str(z['alternate_name']), {'keep_numbers': 1}) for z in misc['alternate_names']].index(team_no_space) ]
                msg = "It appears that {} actually maps to team ID {} ({})".format(d['home_team'], tmp_rec['team_ID'], tmp_rec['actual_name'])
                d['away_team'] = tmp_rec['actual_name']
            
            
            d['league'] = None if row_n_cols <= 6 else clean_league_name(misc['master_sheet_raw_values'][i][6], {'row': misc['master_sheet_raw_values'][i]})
            d['game_type'] = None if row_n_cols <= 7 else misc['master_sheet_raw_values'][i][7]
            d['location'] = None if row_n_cols <= 10 else misc['master_sheet_raw_values'][i][10].replace("'", "")
            d['notes'] = None if row_n_cols <= 11 else misc['master_sheet_raw_values'][i][11]
            d['permits_rules'] = None if row_n_cols <= 12 else misc['master_sheet_raw_values'][i][12]
            d['interleague'] = None if row_n_cols <= 13 else misc['master_sheet_raw_values'][i][13]
            d['doc_umpire_override'] = None if row_n_cols <= 18 else misc['master_sheet_raw_values'][i][18]
            if d['doc_umpire_override'] == "":
                d['doc_umpire_override'] = None
            
            if fn_specs.get('is_full_master', 1):
                if row_n_cols >= 15 and misc['master_sheet_raw_values'][i][14] in ['X', 'x']:
                    d['status'] = "completed"
                elif row_n_cols >= misc['column_locs']['cancelled'] and misc['master_sheet_raw_values'][i][misc['column_locs']['cancelled']] in ['X', 'x', 'Yes', 'Y', 'yes']:
                    d['status'] = "cancelled"
            
            #print(misc['master_sheet_raw_values'][i])
            #print("{:<10}{:<30}{:<30}{:<30}{:<30}{}".format(i+1, misc['master_sheet_raw_values'][i][7], "%s" % d['away_team'], "%s" % d['home_team'], "%s" % d['league'], row_n_cols >= 8 and misc['master_sheet_raw_values'][i][7] in ['Game', 'EOST']))
            is_actual_game_record = 0
            is_scrimmage = 0
            is_rainout = 0
            if row_n_cols >= 8 and misc['master_sheet_raw_values'][i][7] in ['Game', 'EOST']:
                is_actual_game_record = 1
            elif row_n_cols >= 8 and misc['master_sheet_raw_values'][i][6] in ['All Stars'] and misc['master_sheet_raw_values'][i][7] in ['Scrimmage']:
                is_actual_game_record = 1
            elif row_n_cols >= 8 and misc['master_sheet_raw_values'][i][7] in ['Scrimmage']:
                is_scrimmage = 1
            elif row_n_cols >= 8 and misc['master_sheet_raw_values'][i][7] in ['Rainout']:
                is_rainout = 1
            
            d['is_actual_game_record'] = is_actual_game_record   
            d['is_scrimmage_record'] = is_scrimmage    
            if is_actual_game_record or is_scrimmage or is_rainout:
                if d['away_team'] is not None or d['home_team'] is not None or d['league'] is not None:
                    d['hashed_home_team'] = laxref.hash_player_name(str(d['home_team']), {'keep_numbers': 1})
                    d['hashed_away_team'] = laxref.hash_player_name(str(d['away_team']), {'keep_numbers': 1})
                    misc['doc_games'].append(d)
            if 0 and d['game_type'] == "Game":
                zc.print_dict_as_table(d)
            if 0 and d['source_row'] == 875:
                zc.print_dict_as_table(d)
                zc.exit("GM")    
    zc.print_table(misc['doc_games'], {'cutoff*': 20, 'keep_keys': "source_row                    game_date                                                        home_team                     away_team                     league                        location                                               game_type                     status                        db_game_ID                                                        is_actual_game_record         is_scrimmage_record           hashed_home_team              hashed_away_team"})
    print(f"^ misc.doc_games (n={len(misc['doc_games'])})")
    #zc.exit("DOC GMAS")
    return misc
    
IS_SPRING = 1 if datetime.now().month in [12, 1, 2, 3, 4, 5, 6] else 0
if '-fall' in sys.argv:
    IS_SPRING=0
if '-spring' in sys.argv:
    IS_SPRING=1
    
def manually_accept_changes(rec):
    
    # If we could not match to a db game record (based on the ID field stored in the google sheet), then we should check if the inferred record (based on team IDs/league etc) is a clear enough match
    reference_db_record = rec['db_game']
    CAUTION = ""
    if reference_db_record is None:
        reference_db_record = rec['matched_db_game']
        if rec['matched_db_game']['tup_w_only_league_date_only'] == rec['doc_game']['tup_w_only_league_date_only']:
            CAUTION += "There was no db game record that matched to the ID column on the Google Sheet, but we did match to a game from the sheet (based on tup_w_only_league_date_only) that did not have an ID listed; be extra careful before accepting this change"
        else:
            CAUTION += "[WARNING] There was no db game record that matched to the ID column on the Google Sheet, and we could not match to a game from the sheet (based on tup_w_only_league_date_only) that did not have an ID listed; be extra extra careful before accepting this change"
            
    
    
    update_query = "UPDATE SDLL_Games set [] where ID=%s;"
    update_fields = []
    
    update_param = [reference_db_record['ID']]
    
    old_location, new_location, old_game_date, new_game_date, old_home_ID, new_home_ID, old_away_ID, new_away_ID = None, None, None, None, None, None, None, None
    
    
    if reference_db_record['orig_location'] != rec['doc_game']['location']:
        update_fields.append('location')
        old_location = reference_db_record['orig_location']
        new_location = rec['doc_game']['location']
        update_param = [new_location] + update_param
    if reference_db_record['orig_game_date'] != rec['doc_game']['game_date']:
        update_fields.append('game_date')
        old_game_date = reference_db_record['orig_game_date']
        new_game_date = rec['doc_game']['game_date']
        update_param = [new_game_date] + update_param
    if reference_db_record['orig_home_ID'] != rec['doc_game']['home_ID']:
        update_fields.append('home_ID')
        old_home_ID = reference_db_record['orig_home_ID']
        new_home_ID = rec['doc_game']['home_ID']
        update_param = [new_home_ID] + update_param
    if reference_db_record['orig_away_ID'] != rec['doc_game']['away_ID']:
        update_fields.append('away_ID')
        old_away_ID = reference_db_record['orig_away_ID']
        new_away_ID = rec['doc_game']['away_ID']
        update_param = [new_away_ID] + update_param
    update_query = update_query.replace("[]", ", ".join(["%s=%%s" % z for z in update_fields]))
    insert_query = "INSERT INTO SDLL_Game_Updates (active, game_ID, datestamp, old_location, new_location, old_game_date, new_game_date, old_home_ID, new_home_ID, old_away_ID, new_away_ID, added_via) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);"
    insert_param = [1, reference_db_record['ID'], datetime.now(), old_location, new_location, old_game_date, new_game_date, old_home_ID, new_home_ID, old_away_ID, new_away_ID, "manuallyAcceptChanges"]
    
    if update_fields == []:
        laxref.telegram_alert("Error 282")
        zc.exit("NO UPDATES???")
    else:
        print ("Query %s w/ %s" % (update_query, update_param))
        print ("Query %s w/ %s" % (insert_query, insert_param))
        
        if CAUTION not in [None, '']:
            print (f"\n[CAUTION]\n\n{CAUTION}\n")
        if '--allow-updates' in sys.argv:
            cursor = zc.zcursor("SDLL")
            cursor.execute(insert_query, insert_param)
            cursor.execute(update_query, update_param)
            
            cursor.commit(); cursor.close()
            
        elif input("\n Go ahead with above queries? (y/n): ").strip() == "y":
            cursor = zc.zcursor("SDLL")
            cursor.execute(insert_query, insert_param)
            cursor.execute(update_query, update_param)
            
            cursor.commit(); cursor.close()
        else:
            print ("Skipping this update...")
        #zc.exit("RUN QUERY")
        
def manually_resolve_issues(ID_update_types_incorrect_records):
    
    
    for i, rec in enumerate(ID_update_types_incorrect_records):
        print ("\n\nIssue %d / %d" % (i+1, len(ID_update_types_incorrect_records)))
        print ("\n DB Game")
        zc.print_dict_as_table(rec['db_game'])
        print ("\n Matched DB Game")
        zc.print_dict_as_table(rec['matched_db_game'])
        print ("\n Doc Game")
        zc.print_dict_as_table(rec['doc_game'])

        go_on = 1
        while go_on:
            options = []
            if '--allow-updates' in sys.argv:
                options.append({'seq': len(options) + 1, 'title': "Accept (DB updates will be made)", 'desc': None})
            else:
                options.append({'seq': len(options) + 1, 'title': "Review queries (you may accept or reject)", 'desc': None})
            options.append({'seq': len(options) + 1, 'title': "Skip", 'desc': None})
            
            options_str = "\n".join([" - {}. {}".format(z['seq'], z['title']) for z in options])
            
            resp = input("Choose from the following list of options:\n{}\n\n Your choice: ".format(options_str))
            if resp.strip().lower() in [str(z['seq']) for z in options]:
                choice = options[ [str(z['seq']) for z in options].index(resp.strip().lower()) ]
                if choice['seq'] == 1:
                    manually_accept_changes(rec)
                    go_on = 0
                elif choice['seq'] == 2:
                    go_on = 0
   
def _html_send_umpire_day_of_email(game, EMAIL_TYPE):
    html = open(os.path.join(sdll_fldr, 'EmailTemplates', 'UmpirePregameInformation.html'), 'r').read()
    preheader_text = f"{game['location']} @ {game['time_str']}"
    html = html.replace("[local-rules-link]", game['local_rules_link'])
    html = html.replace("[preheader-text]", preheader_text)
    html = html.replace("[field]", game['location'].replace(" ", "+"))
    

    assignment_html = f"""<table style="border-collapse: collapse; width: 100%;">
<tr>
<td style="line-height: 1.5; padding: 6px 0;">
  {game['hi_intro_message']}
</td>
</tr>
<tr>
<td style="line-height: 1.5; padding: 6px 0;">
  Here's the information for your game today at {game['location']} @ {game['time_str']}.
</td>
</tr>
<tr>
<td style="line-height: 1.5; padding: 6px 0;">
  Please try to arrive at the field by {game['arrive_time_str']}.
</td>
</tr>
<tr>
<td style="line-height: 1.5; padding: 6px 0;">
  Today, you are working a {game['league_str']} game. 
  The {game['home_team_w_coach']} are the home team and the away team is {game['away_team_w_coach']}.
</td>
</tr>
</table>"""
    
    
    html = html.replace("[weatherbug-string]", field_zip_codes.get(game['location'], defaultZip))
    
    html = html.replace("[ASSIGNMENT-DETAILS]", assignment_html)
    
    f = open(os.path.join(sdll_fldr, 'EmailTemplates', 'test.html'), 'w', encoding='utf-8')
    f.write(html); f.close()
    ##zc.exit("HTML WRITTEN")
    
    subj = "Information for your SDLL game today"
    if '--day-ahead' in sys.argv and '--admin-version' in sys.argv:
        subj = "[TOMORROW PREVIEW / ADMIN-VERSION] Information for your SDLL game [today]"
        
    send_it = 1
    if '--use-real-email-addresses' in sys.argv:
        resp = input("Send email to %s: (y/n/skip) " % game['umpire_email_addresses'])
        if resp == "n":
            zc.exit("Exiting...")
        elif resp == "skip":
            send_it = 0
    if send_it:
    
        cursor = zc.zcursor("SDLL")
        query = "INSERT INTO SDLL_Umpire_Notifications (game_ID, active, send_date, email_type, umpire_emails) VALUES (%s, %s, %s, %s, %s);"
        param = [game['game_ID'], 1, datetime.now(), EMAIL_TYPE, "|".join(game['umpire_email_addresses'])]
        print ("Query %s w/ %s" % (query, param))
        cursor.execute(query, param)
        send_email(f"<HTML>{html}</HTML>", {'subject': subj, 'to': game['umpire_email_addresses']})
        
        if '-quiet' not in sys.argv and '--use-real-email-addresses' in sys.argv:
            cursor.commit()
        cursor.close()

def get_update_commentary_history_from_list(g, fn_specs):
    res = None
    
    if g.get('updates', []) != []:
        
        d = {}
        g['updates'].sort(key=lambda x:x['datestamp'])
        
        
        tmp = [z for z in g['updates'] if z['old_duration_in_hours'] not in ['', None]]
        d['orig_duration_in_hours'] = None if tmp == [] else tmp[0]['old_duration_in_hours']
        tmp = [z for z in g['updates'] if z['new_duration_in_hours'] not in ['', None]]
        d['final_duration_in_hours'] = None if tmp == [] else tmp[-1]['new_duration_in_hours']
        
        tmp = [z for z in g['updates'] if z['old_location'] not in ['', None]]
        d['orig_location'] = None if tmp == [] else tmp[0]['old_location']
        tmp = [z for z in g['updates'] if z['new_location'] not in ['', None]]
        d['final_location'] = None if tmp == [] else tmp[-1]['new_location']
        
        tmp = [z for z in g['updates'] if z['old_away_ID'] not in ['', None]]
        d['orig_away_ID'] = None if tmp == [] else tmp[0]['old_away_ID']
        tmp = [z for z in g['updates'] if z['new_away_ID'] not in ['', None]]
        d['final_away_ID'] = None if tmp == [] else tmp[-1]['new_away_ID']
        
        tmp = [z for z in g['updates'] if z['old_home_ID'] not in ['', None]]
        d['orig_home_ID'] = None if tmp == [] else tmp[0]['old_home_ID']
        tmp = [z for z in g['updates'] if z['new_home_ID'] not in ['', None]]
        d['final_home_ID'] = None if tmp == [] else tmp[-1]['new_home_ID']
        
        tmp = [z for z in g['updates'] if z['old_game_date'] not in ['', None]]
        d['orig_game_date'] = None if tmp == [] else tmp[0]['old_game_date']
        tmp = [z for z in g['updates'] if z['new_game_date'] not in ['', None]]
        d['final_game_date'] = None if tmp == [] else tmp[-1]['new_game_date']
        
        d['orig_game_date_str'] = None if d['orig_game_date'] is None else d['orig_game_date'].strftime("%a %b %d").replace(" 0", " ")
        d['final_game_date_str'] = None if d['final_game_date'] is None else d['final_game_date'].strftime("%a %b %d").replace(" 0", " ")
        d['orig_time_str'] = None if d['orig_game_date'] is None else dt_to_time_str(d['orig_game_date'])
        d['final_time_str'] = None if d['final_game_date'] is None else dt_to_time_str(d['final_game_date'])
        
        away_ID_changed = 1 if d['orig_away_ID'] != d['final_away_ID'] else 0
        home_ID_changed = 1 if d['orig_home_ID'] != d['final_home_ID'] else 0
        location_changed = 1 if  None not in [d['orig_location'], d['final_location']] and  d['orig_location'] != d['final_location'] else 0
        duration_in_hours_changed = 1 if  None not in [d['orig_duration_in_hours'], d['final_duration_in_hours']] and  d['orig_duration_in_hours'] != d['final_duration_in_hours'] else 0
        date_changed = 1 if  None not in [d['orig_game_date_str'], d['final_game_date_str']] and  d['orig_game_date_str'] != d['final_game_date_str'] else 0
        time_changed = 1 if date_changed or  None not in [d['orig_time_str'], d['final_time_str']] and  d['orig_time_str'] != d['final_time_str'] else 0
        if location_changed and date_changed and time_changed:
            res = f"Game was originally scheduled for {d['orig_time_str']} on {d['orig_game_date_str']} @ {d['orig_location']}"
        elif location_changed and not date_changed and not time_changed:
            res = f"Game was originally scheduled at the same time, but at {d['orig_location']}"
        elif location_changed and date_changed and not time_changed:
            res = f"Game was originally scheduled for the same time on {d['orig_game_date_str']} @ {d['orig_location']}"
        elif location_changed and not date_changed and time_changed:
            res = f"Game was originally scheduled for {d['orig_time_str']} @ {d['orig_location']}"
        
        elif not location_changed and not date_changed and time_changed:
            res = f"Game was originally scheduled for {d['orig_time_str']}"
        elif not location_changed and date_changed and not time_changed:
            res = f"Game was originally scheduled for the same time on {d['orig_game_date_str']}"
        elif not location_changed and date_changed and time_changed:
            res = f"Game was originally scheduled for {d['orig_time_str']} on {d['orig_game_date_str']}"
        elif not location_changed and not date_changed and not time_changed and duration_in_hours_changed:
            res = None # No need to update umpires about this since the time they need to be at the field has not changed
        elif not location_changed and not date_changed and not time_changed and not duration_in_hours_changed and (home_ID_changed or away_ID_changed):
            res = None # No need to update umpires about team changes since the time they need to be at the field has not changed
        
        elif datetime.now().strftime("%Y%m%d") == "20260511":
            res = None
        else:
            
            zc.print_dict_as_table(d)
            zc.print_table(g['updates'], {'cutoff*': 20})
            print ("{:<30}{}".format("location_changed", location_changed))
            print ("{:<30}{}".format("duration_in_hours_changed", duration_in_hours_changed))
            print ("{:<30}{}".format("date_changed", date_changed))
            print ("{:<30}{}".format("time_changed", time_changed))
            laxref.telegram_alert("[SDLL FATAL]\n\nCouldn't parse the game updates into a coherent description")
            zc.exit("FATAL 752")
        
        #zc.exit("FDS")
    
    return res
    
def _html_send_umpire_upcoming_schedule_email(umpire, EMAIL_TYPE):
    html = open(os.path.join(sdll_fldr, 'EmailTemplates', 'UmpireUpcomingSchedule.html'), 'r').read()
    preheader_text = f"You have {len(umpire['games'])} games coming up this week"
    #html = html.replace("[local-rules-link]", game['local_rules_link'])
    html = html.replace("[preheader-text]", preheader_text.replace(" 1 games", " 1 game"))
    #html = html.replace("[field]", game['location'].replace(" ", "+"))
    

    assignment_html = f"""<table style="border-collapse: collapse; width: 100%;">
<tr>
<td style="line-height: 1.5; padding: 6px 0;">
  {umpire['hi_intro_message']}
</td>
</tr>
<tr>
<td style="line-height: 1.5; padding: 6px 0;">
  Here's your upcoming schedule of {len(umpire['games'])} SDLL games over the coming week. If you see anything that looks inaccurate, let me know.
</td>
</tr>
<tr>
<td style="line-height: 1.5; padding: 6px 0;">{umpire['games_html']}</td>
</tr>
<tr>
</tr>
</table>"""
    assignment_html = assignment_html.replace("of 1 SDLL games", "of SDLL games")
    
    
    #html = html.replace("[weatherbug-string]", field_zip_codes.get(game['location'], defaultZip))
    
    html = html.replace("[GAMES-TABLE]", assignment_html)
    
    f = open(os.path.join(sdll_fldr, 'EmailTemplates', 'test.html'), 'w', encoding='utf-8')
    f.write(html); f.close()
    ##zc.exit("HTML WRITTEN")
    
    subj = "Confirming your upcoming SDLL games"
    if '--day-ahead' in sys.argv and '--admin-version' in sys.argv:
        subj = "[TOMORROW PREVIEW / ADMIN-VERSION] Confirming your upcoming SDLL games"
        
    send_it = 1
    if '--use-real-email-addresses' in sys.argv:
        resp = input("Send email to %s: (y/n/skip) " % umpire['umpire_email_addresses'])
        if resp == "n":
            zc.exit("Exiting...")
        elif resp == "skip":
            send_it = 0
    if send_it:
    
        cursor = zc.zcursor("SDLL")
        query = "INSERT INTO SDLL_Umpire_Notifications (active, send_date, email_type, umpire_emails) VALUES (%s, %s, %s, %s);"
        param = [1, datetime.now(), EMAIL_TYPE, "|".join(umpire['umpire_email_addresses'])]
        print ("Query %s w/ %s" % (query, param))
        cursor.execute(query, param)
        send_email(f"<HTML>{html}</HTML>", {'subject': subj, 'to': umpire['umpire_email_addresses']})
        
        if '-quiet' not in sys.argv and '--use-real-email-addresses' in sys.argv:
            cursor.commit()
        cursor.close()


league_strings = {}
league_strings['BB Intermediate'] = "Intermediate (Kid Pitch BB)"
league_strings['BB AAA'] = "AAA (Kid Pitch BB)"
league_strings['BB AA'] = "AA (Kid Pitch BB)"
league_strings['BB A'] = "Upper Machine Pitch BB"
league_strings['BB Rookie'] = "Lower Machine Pitch BB"
league_strings['SB Rookie'] = "Lower Machine Pitch SB"

local_rules = {}
local_rules['BB Intermediate'] = "https://docs.google.com/document/d/1UkkwToe73q11W56QHqAKn5bg54F3Dd95_HFgkY0jLqA/edit?usp=sharing"
local_rules['BB AAA'] = "https://docs.google.com/document/d/1EgrTOgyVpyckRJGqXNs9Kz3E8xDiDoWc_vhJffbCqgQ/edit?usp=sharing"
local_rules['BB AA'] = "https://docs.google.com/document/d/1wCZ1MUXID0hS5kx3tdk635iu3zL5xMdWaKKZuOOQfTs/edit?usp=sharing"
local_rules['BB A'] = "https://docs.google.com/document/d/1ZQh4K49FFATuNXSchtWYB1xRkDtDB0Q7N37ZIzYFjSk/edit?usp=sharing"
local_rules['BB Rookie'] = "https://docs.google.com/document/d/1_kIORPh9d2M4JI7oIVJDELcIr1zxjVzI8bVBvqmWXSM/edit?usp=sharing"
local_rules['SB Rookie'] = "https://docs.google.com/document/d/1J8WdiDF7nR_bGArUyewAKUOudBk7qwVe6W5JadEYBY4/edit?usp=sharing"
default_rules_link = "https://tshq.bluesombrero.com/Default.aspx?tabid=2180637"




field_zip_codes = {}
defaultZip = "durham-nc-27707"
field_zip_codes['Herndon 1'] = "durham-nc-27713"
field_zip_codes['Parkwood'] = "durham-nc-27713"
field_zip_codes['Herndon 2'] = "durham-nc-27713"
field_zip_codes['Southern Boundaries 2'] = "durham-nc-27707"
field_zip_codes['Hillside High School'] = "durham-nc-27707"
field_zip_codes['Alston Ridge'] = "cary-nc-27519"
field_zip_codes['Pineywood Park'] = "durham-nc-27713"
field_zip_codes['Sherwood Githens Middle School'] = "durham-nc-27707"
field_zip_codes['Ephesus Park'] = "chapel-hill-nc-27517"
field_zip_codes['Lowes Grove'] = ""
field_zip_codes['Cresset Christian Academy'] = ""
field_zip_codes['Cedar Falls Park 1'] = ""
field_zip_codes['Riverside High School'] = ""
field_zip_codes['Wrightwood Park'] = ""
field_zip_codes['Northwood HS Softball Field'] = ""
field_zip_codes['BCLL Field #2'] = ""
field_zip_codes['Shepard Middle School'] = ""
field_zip_codes['BCLL Field #3'] = ""
field_zip_codes['Morrisville Community Park Field 1'] = ""
field_zip_codes['Southern Boundaries 1'] = ""
field_zip_codes['BCLL Field #4'] = ""
field_zip_codes['BCLL Field #1'] = ""
field_zip_codes['Seaforth Softball Field'] = ""
field_zip_codes['Cedar Falls Park 3'] = ""
field_zip_codes['Valley Springs Field 2'] = ""
field_zip_codes['Cedar Falls Park 2'] = ""
field_zip_codes['Northeast District Park'] = ""
field_zip_codes['Riverside High'] = ""
field_zip_codes['TBD'] = ""
field_zip_codes['Whippoorwill Park'] = ""
from pprint import pprint
        
def dt_to_time_str(dt):
    res = dt.strftime("%I:%M %p").lower()
    if res.startswith("0"):
        res = res[1:]
    return res
    


def check_for_all_star_announcement():
    print ("--check-for-all-star-announcement")
    # python C:\Users\zcapo\Documents\workspace\SDLL\scratchpad.py  --check-for-all-star-announcement
    print ("Importing libs...")
    import selenium, statistics
    from selenium import webdriver
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support.ui import Select
    from selenium.webdriver.common.by import By

    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    import urllib3, json, io
    from fuzzywuzzy import fuzz

    import time
    import datetime, os
    options = webdriver.FirefoxOptions()

    if '--headless' in sys.argv or '-headless' in sys.argv:
        options.add_argument("-headless")
        
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("ignore-certificate-errors")

    options.add_argument('--ignore-ssl-errors')
    options.add_argument('ignore-ssl-errors')

    
    options.binary_location = "C:\\Program Files\\Mozilla Firefox\\firefox.exe"
    
    url = "https://tshq.bluesombrero.com/Default.aspx?tabid=2777284"
    
    browser = webdriver.Firefox(options=options)
    browser.get(url); print ("Page loaded, retrieving page source")
    txt = zc.remove_non_ascii(browser.page_source)
    browser.close()
    
    found_will = ('Will Capozzi' in txt)
    found_jack = ('Jack Capozzi' in txt)
    print (f"Will Capozzi: {('Will Capozzi' in txt)}")
    print (f"Jack Capozzi: {('Jack Capozzi' in txt)}")
    
    if found_jack and found_will:
        laxref.telegram_alert("Orange team has been announced!!!")
    elif 0 and not found_jack and found_will:
        laxref.telegram_alert("Only Green team has been announced!!!")
    
    
def send_umpire_upcoming_schedule_email():
    print ("--send-umpire-upcoming-schedule-email")
    # python C:\Users\zcapo\Documents\workspace\SDLL\scratchpad.py  --send-umpire-upcoming-schedule-email --admin-version
    # python C:\Users\zcapo\Documents\workspace\SDLL\scratchpad.py  --send-umpire-upcoming-schedule-email
    # python C:\Users\zcapo\Documents\workspace\SDLL\scratchpad.py  --send-umpire-upcoming-schedule-email --use-real-email-addresses
    # python C:\Users\zcapo\Documents\workspace\SDLL\scratchpad.py  --send-umpire-upcoming-schedule-email --use-real-email-addresses -marti --ignore-missing-games & python C:\Users\zcapo\Documents\workspace\SDLL\scratchpad.py  --send-umpire-upcoming-schedule-email --use-real-email-addresses -vance --ignore-missing-games
    # python C:\Users\zcapo\Documents\workspace\SDLL\scratchpad.py  --send-umpire-upcoming-schedule-email --admin-version -marti
    
    
    misc = {}
    
    start_dt = (datetime.now() + timedelta(hours=0))
    end_dt = (datetime.now() + timedelta(days=7))
    
    umpires = []
    misc = read_master_schedule()
    orig_games = misc['doc_games']
    games_hashMap = {}
    for g in orig_games:
        games_hashMap[f"{g['game_date']}{g['home_team']}{g['away_team']}{g['location']}"] = g['db_game_ID']
    
    orig_games = [z for z in orig_games if start_dt < z['game_date'] < end_dt]
    zc.print_table(orig_games, {'cutoff*': 20, 'keep_keys': 'location db_game_ID  game_date home_team away_team league'})
    print("^ MASTER GAMES")
        
    cursor = zc.zcursor("SDLL")
    game_IDs = None
    if '-marti' in sys.argv:
        misc, service = read_from_google_sheet("martiSheet", misc, {})
        misc = convert_master_sheet_data_to_games(misc, service, {'version': 1, 'is_full_master': 0})
        
        upcoming_games = [z for z in misc['doc_games'] if start_dt < z['game_date'] < end_dt]
        if upcoming_games == []:
            return
        for g in upcoming_games:
            g['db_game_ID'] = games_hashMap.get(f"{g['game_date']}{g['home_team']}{g['away_team']}{g['location']}")
        zc.print_table(upcoming_games, {'cutoff*': 20, 'keep_keys': 'location db_game_ID  game_date home_team away_team league'})
        print("^ AMRTI GAMES")
        umpire = {'hi_intro_message': 'Hi Marti,', 'games': upcoming_games, 'umpire_email_addresses': ["m2s1@hotmail.com", "schedule.sdll@gmail.com"]}
        #umpire = {'hi_intro_message': 'Hi Marti,', 'games': upcoming_games, 'umpire_email_addresses': ["sdll.umpires@gmail.com", "schedule.sdll@gmail.com"]}
        if upcoming_games != []:
            print (sorted(upcoming_games[0].keys()))
        game_IDs = [z['db_game_ID'] for z in upcoming_games]
        print (game_IDs)
        game_IDs_str = ",".join(map(str, game_IDs))
        game_updates_query = f"""SELECT game_ID, datestamp, old_location, new_location, old_game_date_str, new_game_date_str, added_via, old_home_ID, new_home_ID, old_away_ID, new_away_ID, old_game_date, new_game_date, new_duration_in_hours, old_duration_in_hours from SDLL_Game_Updates 
            WHERE active and game_ID IN ({game_IDs_str});
        ;""".replace(" THEN None", " THEN NULL")
        cursor = zc.zcursor("SDLL")
        game_updates = cursor.defaultdict_query_results(game_updates_query, [], 'game_ID')
        cursor.close()
        for g in upcoming_games:
            g['updates'] = game_updates.get(g['db_game_ID'], [])
            g['updates_history'] = None
            if len(g['updates']) > 2:
                tmp_ = get_update_commentary_history_from_list(g, {})
                
                g['updates_history'] = tmp_
                
        umpires.append(umpire)
                
        
        
    elif '-vance' in sys.argv:
        misc, service = read_from_google_sheet("vanceSheet", misc, {})
        misc = convert_master_sheet_data_to_games(misc, service, {'version': 1, 'is_full_master': 0})
        
        upcoming_games = [z for z in misc['doc_games'] if start_dt < z['game_date'] < end_dt]
        if upcoming_games == []:
            return
        for g in upcoming_games:
            g['db_game_ID'] = games_hashMap.get(f"{g['game_date']}{g['home_team']}{g['away_team']}{g['location']}")
        umpire = {'hi_intro_message': 'Hi Vance,', 'games': upcoming_games, 'umpire_email_addresses': ["vance.Stilley@dynamicofficials.com", "schedule.sdll@gmail.com"]}
        #umpire = {'hi_intro_message': 'Hi Vance,', 'games': upcoming_games, 'umpire_email_addresses': ["sdll.umpires@gmail.com", "schedule.sdll@gmail.com"]}
        if upcoming_games != []:
            print (sorted(upcoming_games[0].keys()))
        game_IDs = [z['db_game_ID'] for z in upcoming_games]
        print (game_IDs)
        game_IDs_str = ",".join(map(str, [z for z in game_IDs if z is not None]))
        game_updates_query = f"""SELECT game_ID, datestamp, old_location, new_location, old_game_date_str, new_game_date_str, added_via, old_home_ID, new_home_ID, old_away_ID, new_away_ID, old_game_date, new_game_date, new_duration_in_hours, old_duration_in_hours from SDLL_Game_Updates 
            WHERE active and game_ID IN ({game_IDs_str});
        ;""".replace(" THEN None", " THEN NULL")
        cursor = zc.zcursor("SDLL")
        game_updates = cursor.defaultdict_query_results(game_updates_query, [], 'game_ID')
        cursor.close()
        for g in upcoming_games:
            g['updates'] = game_updates.get(g['db_game_ID'], [])
            g['updates_history'] = None
            if len(g['updates']) > 2:
                g['updates_history'] = get_update_commentary_history_from_list(g, {})
        umpires.append(umpire)
        zc.print_table(upcoming_games, {'cutoff*': 20, 'keep_keys': 'location  game_date home_team away_team league'})
        print("^ VANCE GAMES")
        
    elif '--between-four-and-seven-hours-from-now' in sys.argv:
        query = "SELECT a.ID game_ID from SDLL_Games a where a.active and a.game_date >= STR_TO_DATE(%s, '%%Y-%%m-%%d %%H:%%i') and a.game_date < STR_TO_DATE(%s, '%%Y-%%m-%%d %%H:%%i');"

        param = [start_dt.strftime("%Y-%m-%d %H:%M"),end_dt.strftime("%Y-%m-%d %H:%M")]
        print ("Query %s w/ %s" % (query, param))
        game_IDs = [z['game_ID'] for z in cursor.dqr(query, param)]
        #print ("Game IDs: %s" % game_IDs)
        #zc.exit("HOURS")
    elif '--between-two-and-seven-hours-from-now' in sys.argv:
        query = "SELECT a.ID game_ID from SDLL_Games a where a.active and a.game_date >= STR_TO_DATE(%s, '%%Y-%%m-%%d %%H:%%i') and a.game_date < STR_TO_DATE(%s, '%%Y-%%m-%%d %%H:%%i');"
        if '--day-ahead' in sys.argv and '--admin-version' in sys.argv:
            start_dt = (datetime.now() + timedelta(hours=0 + 24))
            end_dt = (datetime.now() + timedelta(hours=7 + 24))
            
        else:
            start_dt = (datetime.now() + timedelta(hours=2))
            end_dt = (datetime.now() + timedelta(hours=7))
        param = [start_dt.strftime("%Y-%m-%d %H:%M"),end_dt.strftime("%Y-%m-%d %H:%M")]
        print ("Query %s w/ %s" % (query, param))
        game_IDs = [z['game_ID'] for z in cursor.dqr(query, param)]
        #print ("Game IDs: %s" % game_IDs)
        #zc.exit("HOURS")
    elif '--next-seven-hours' in sys.argv:
        query = "SELECT a.ID game_ID from SDLL_Games a where a.active and a.game_date >= STR_TO_DATE(%s, '%%Y-%%m-%%d %%H:%%i') and a.game_date < STR_TO_DATE(%s, '%%Y-%%m-%%d %%H:%%i');"
        if '--day-ahead' in sys.argv and '--admin-version' in sys.argv:
            start_dt = (datetime.now() + timedelta(hours=0 + 24))
            end_dt = (datetime.now() + timedelta(hours=7 + 24))
            
        else:
            start_dt = (datetime.now() + timedelta(hours=0))
            end_dt = (datetime.now() + timedelta(hours=7))
        param = [start_dt.strftime("%Y-%m-%d %H:%M"),end_dt.strftime("%Y-%m-%d %H:%M")]
        print ("Query %s w/ %s" % (query, param))
        game_IDs = [z['game_ID'] for z in cursor.dqr(query, param)]
        #print ("Game IDs: %s" % game_IDs)
        #zc.exit("HOURS")
    else:
        game_IDs = [int(z) for z in sys.argv[sys.argv.index('--game-ID') + 1].split("|")]
        
    if len(umpires) == 0:
        return
        
    EMAIL_TYPE="upcoming-schedule"
    query = "SELECT send_date, email_type, umpire_emails from SDLL_Umpire_Notifications a where a.active and a.email_type=%s;"
    param = [EMAIL_TYPE]
    print ("Query %s w/ %s" % (query, param))
    misc['send_notification_records'] = {z['send_date'].strftime("%Y%m%d") + "-" + z['umpire_emails']: z for z in cursor.dqr(query, param)}

    cursor.close()
    
    
    assignr_games = {str(z['id']): z for z in read_assignr_games()}
    #zc.print_dict_as_table(assignr_games[0]);

    #zc.exit("AG")
    
    #game = {'location': "Parkwood", 'time_str': "3pm", 'arrive_time_str': "2:45pm", 'league_str': "Cactus (Kid Pitch)", "home_team_w_coach": "Orioles (head coach is John Smith)", "away_team_w_coach": "Red Sox (head coach is Mark Jones)", 'local_rules_link': "https://tshq.bluesombrero.com/Default.aspx?tabid=2180637"}
    for g in umpires:
        
        
        
        zc.print_dict_as_table(g)
        
        if '--use-real-email-addresses' not in sys.argv:
            g['umpire_email_addresses'] = ['sdll.umpires@gmail.com']
        
        g['email_sent'] = 0 #1 if misc['send_notification_records'].get(g['game_ID']) is not None else 0
        
        dates = defaultdict(list)
        umpire['games'].sort(key=lambda x:x['game_date'])
        for gm in umpire['games']:
            gm_dt = ("%s%s" % (gm['game_date'].strftime("%a %b %d"), zc.get_number_suffix(gm['game_date'].day))).replace(" 0", " ")
            gm['time_str'] = dt_to_time_str(gm['game_date'])
            dates[gm_dt].append(gm)
        
        html = ""
        for dt in dates:
            gms = dates.get(dt)
            gms.sort(key=lambda x:x['league'])
            leagues = defaultdict(list)
            for gm in gms:
                
                if '--include-update-history' in sys.argv and gm['updates_history'] not in [None, '']:
                    
                    gm['html'] = f"<tr><td style='border-bottom:solid 1px #EEE; padding-left:20px;'>{gm['time_str']} @ {gm['location']}<BR><p style='font-style:italic;'>{gm['updates_history']}</p></td></tr>"
                else:
                    gm['html'] = f"<tr><td style='border-bottom:solid 1px #EEE; padding-left:20px;'>{gm['time_str']} @ {gm['location']}</td></tr>"
                leagues[gm['league']].append(gm['html'])
            
            html += f"<tr><td><h3>{dt} ({len(gms)} games)</h3></td></tr>".replace("(1 games)", "(1 game)")
            for l in leagues:
                gms = leagues[l]
                
                html += f"<tr><td style='padding-left:10px;'><h4>{l}</h4></td></tr>"
                html += "".join(gms)
            
        g['games_html'] = html
    print ("Umpires to send")
    zc.print_table(umpires, {'keep_keys': ['away_team', 'home_team', 'game_date', 'location', 'league']})
    
        
    for ig, umpire in enumerate(umpires):    
        print ("Umpire %d/%d" % (ig+1, len(umpires)))
        
        _html_send_umpire_upcoming_schedule_email(umpire, EMAIL_TYPE)
        
        
            
    zc.exit("DONE EMAIL SENDS")
    
def send_umpire_day_of_email():
    print ("--send-umpire-day-of-email")
    # python C:\Users\zcapo\Documents\workspace\SDLL\scratchpad.py  --send-umpire-day-of-email --between-two-and-seven-hours-from-now 
    # python C:\Users\zcapo\Documents\workspace\SDLL\scratchpad.py  --send-umpire-day-of-email --next-seven-hours --use-real-email-addresses
    
    
    misc = {}
    misc, service = read_from_google_sheet("all_games_master_doc", misc, {})
    misc, service = read_from_google_sheet("teamKey", misc, {})
    misc = convert_master_sheet_data_to_games(misc, service, {'version': 1})
    
    
    cursor = zc.zcursor("SDLL")
    game_IDs = None
    
    if '--between-three-and-six-hours-from-now' in sys.argv:
        query = "SELECT a.ID game_ID from SDLL_Games a where a.active and a.game_date >= STR_TO_DATE(%s, '%%Y-%%m-%%d %%H:%%i') and a.game_date < STR_TO_DATE(%s, '%%Y-%%m-%%d %%H:%%i');"
        start_dt = (datetime.now() + timedelta(hours=3))
        end_dt = (datetime.now() + timedelta(hours=6))
        param = [start_dt.strftime("%Y-%m-%d %H:%M"),end_dt.strftime("%Y-%m-%d %H:%M")]
        print ("Query %s w/ %s" % (query, param))
        game_IDs = [z['game_ID'] for z in cursor.dqr(query, param)]
        #print ("Game IDs: %s" % game_IDs)
        #zc.exit("HOURS")
    elif '--between-four-and-seven-hours-from-now' in sys.argv:
        query = "SELECT a.ID game_ID from SDLL_Games a where a.active and a.game_date >= STR_TO_DATE(%s, '%%Y-%%m-%%d %%H:%%i') and a.game_date < STR_TO_DATE(%s, '%%Y-%%m-%%d %%H:%%i');"
        if '--day-ahead' in sys.argv and '--admin-version' in sys.argv:
            start_dt = (datetime.now() + timedelta(hours=0 + 24))
            end_dt = (datetime.now() + timedelta(hours=7 + 24))
            
        else:
            start_dt = (datetime.now() + timedelta(hours=4))
            end_dt = (datetime.now() + timedelta(hours=7))
        param = [start_dt.strftime("%Y-%m-%d %H:%M"),end_dt.strftime("%Y-%m-%d %H:%M")]
        print ("Query %s w/ %s" % (query, param))
        game_IDs = [z['game_ID'] for z in cursor.dqr(query, param)]
        #print ("Game IDs: %s" % game_IDs)
        #zc.exit("HOURS")
    elif '--between-two-and-seven-hours-from-now' in sys.argv:
        query = "SELECT a.ID game_ID from SDLL_Games a where a.active and a.game_date >= STR_TO_DATE(%s, '%%Y-%%m-%%d %%H:%%i') and a.game_date < STR_TO_DATE(%s, '%%Y-%%m-%%d %%H:%%i');"
        if '--day-ahead' in sys.argv and '--admin-version' in sys.argv:
            start_dt = (datetime.now() + timedelta(hours=0 + 24))
            end_dt = (datetime.now() + timedelta(hours=7 + 24))
            
        else:
            start_dt = (datetime.now() + timedelta(hours=2))
            end_dt = (datetime.now() + timedelta(hours=7))
        param = [start_dt.strftime("%Y-%m-%d %H:%M"),end_dt.strftime("%Y-%m-%d %H:%M")]
        print ("Query %s w/ %s" % (query, param))
        game_IDs = [z['game_ID'] for z in cursor.dqr(query, param)]
        #print ("Game IDs: %s" % game_IDs)
        #zc.exit("HOURS")
    elif '--next-seven-hours' in sys.argv:
        query = "SELECT a.ID game_ID from SDLL_Games a where a.active and a.game_date >= STR_TO_DATE(%s, '%%Y-%%m-%%d %%H:%%i') and a.game_date < STR_TO_DATE(%s, '%%Y-%%m-%%d %%H:%%i');"
        if '--day-ahead' in sys.argv and '--admin-version' in sys.argv:
            start_dt = (datetime.now() + timedelta(hours=0 + 24))
            end_dt = (datetime.now() + timedelta(hours=7 + 24))
            
        else:
            start_dt = (datetime.now() + timedelta(hours=0))
            end_dt = (datetime.now() + timedelta(hours=7))
        param = [start_dt.strftime("%Y-%m-%d %H:%M"),end_dt.strftime("%Y-%m-%d %H:%M")]
        print ("Query %s w/ %s" % (query, param))
        game_IDs = [z['game_ID'] for z in cursor.dqr(query, param)]
        #print ("Game IDs: %s" % game_IDs)
        #zc.exit("HOURS")
    else:
        game_IDs = [int(z) for z in sys.argv[sys.argv.index('--game-ID') + 1].split("|")]
        
    if len(game_IDs) == 0:
        return
    EMAIL_TYPE="day-of-info"
    query = "SELECT game_ID, send_date, email_type, umpire_emails from SDLL_Umpire_Notifications a, SDLL_Games b where b.ID=a.game_ID and a.active and b.active and b.is_spring=%s and b.year=%s and a.email_type=%s;"
    param = [IS_SPRING, datetime.now().year, EMAIL_TYPE]
    print ("Query %s w/ %s" % (query, param))
    misc['send_notification_records'] = {z['game_ID']: z for z in cursor.dqr(query, param)}
    
    sub_query = " or ".join(["a.ID=%s" % z for z in game_IDs])
    query = f"""Select a.ID game_ID, a.game_date, a.location, a.league, a.assignr_ID
    , c.team_ID home_ID,  c.display_name home_team
    , b.team_ID away_ID,  b.display_name away_team
    from SDLL_Games a LEFT JOIN SDLL_Team_Seasons b ON b.team_ID=a.away_ID  LEFT JOIN SDLL_Team_Seasons c ON c.team_ID=a.home_ID where 
    ({sub_query})
    ;"""
    
    param = []
    print ("Query %s w/ %s" % (query, param))
    games = cursor.dqr(query, param)
    cursor.close()
    
    
    assignr_games = {str(z['id']): z for z in read_assignr_games()}
    #zc.print_dict_as_table(assignr_games[0]);

    #zc.exit("AG")
    
    #game = {'location': "Parkwood", 'time_str': "3pm", 'arrive_time_str': "2:45pm", 'league_str': "Cactus (Kid Pitch)", "home_team_w_coach": "Orioles (head coach is John Smith)", "away_team_w_coach": "Red Sox (head coach is Mark Jones)", 'local_rules_link': "https://tshq.bluesombrero.com/Default.aspx?tabid=2180637"}
    for g in games:
        g['time_str'] = g['game_date'].strftime("%I:%M%p").replace(":00", "")
        g['arrive_time_str'] = (g['game_date']-timedelta(seconds=900)).strftime("%I:%M%p").replace(":00", "")
        if g['time_str'].startswith("0"): g['time_str'] = g['time_str'][1:]
        if g['arrive_time_str'].startswith("0"): g['arrive_time_str'] = g['arrive_time_str'][1:]
        
        g['league_str'] = league_strings.get(g['league'], g['league'])
        g['local_rules_link'] = local_rules.get(g['league'], default_rules_link)
        
        
        
        g['no_umpire_assigned'] = 0
        
        home_coaches = misc['coaches_by_team'].get(g['home_team'])
        away_coaches = misc['coaches_by_team'].get(g['away_team'])
        print("home coaches")
        print (home_coaches)
        print("away coaches")
        print (away_coaches)
        
        home_coach_str = "UNKNOWN"
        away_coach_str = "UNKNOWN"
        if home_coaches is not None:
            home_coach_str = home_coaches[0]['head_coach_name']
        if away_coaches is not None:
            away_coach_str = away_coaches[0]['head_coach_name']
        
        
        assignr_game = assignr_games.get(str(g['assignr_ID']))
        if assignr_game is None:
            g['found_in_assignr'] = 0
        else:
            g['found_in_assignr'] = 1
            g['umpire_email_addresses'] = []
            g['umpires'] = [z['_embedded']['official'] for z in assignr_game["_embedded"]['assignments'] if z.get("_embedded") is not None and z['_embedded'].get("official") is not None]
            print (json.dumps(g['umpires'], default=zc.json_handler, indent=1))
            g['umpire_first_names_list'] = []
            g['no_umpire_assigned'] = 1
            for umpire in g['umpires']:
                
                UMPIRE_ID=umpire['id']
                url = f"https://api.assignr.com/api/v2/users/{UMPIRE_ID}"
                print (url)
                g['no_umpire_assigned'] = 0
                headers = {"accept": "application/json"}
                #response = requests.get(url, headers=headers)
                response = assignr_request(url)
                print(response)
                print ("Email Addresses:")
                print (response.get('email_addresses'))
                g['umpire_email_addresses'] += response.get('email_addresses')
                g['umpire_first_names_list'].append(response.get("first_name"))
                g['hi_intro_message'] = "Hi"
                if None not in g['umpire_first_names_list']:
                    g['hi_intro_message'] = "Hi {},".format(zc.list_to_sentence(g['umpire_first_names_list']))
                

            
            print ("Umpires")
            
            print(assignr_game['umpires'])
            
        if home_coach_str == "UNKNOWN":
            g['home_team_w_coach'] = f"{g['home_team']} (head coach is not listed)"
        else:
            g['home_team_w_coach'] = f"{g['home_team']} (head coach is {home_coach_str})"
        if away_coach_str == "UNKNOWN":
            g['away_team_w_coach'] = f"{g['away_team']} (head coach is not listed)"
        else:
            g['away_team_w_coach'] = f"{g['away_team']} (head coach is {away_coach_str})"
        zc.print_dict_as_table(g)
        
        if '--use-real-email-addresses' not in sys.argv:
            g['umpire_email_addresses'] = ['sdll.umpires@gmail.com']
        
        g['email_sent'] = 1 if misc['send_notification_records'].get(g['game_ID']) is not None else 0
        
        # We know we aren't going to have email addresses for teams that are not part of SDLL (like ECLL teams); rather than causing an error, we should fall back on the "head coach is not listed" language
        home_is_known_unknown = 0 
        away_is_known_unknown = 0 
        if g.get('home_team') is None:
            
            home_is_known_unknown = 1
        elif "ECLL" in g['home_team']:
            home_is_known_unknown = 1
        elif "Chapel Hill Rec" in g['home_team']:
            home_is_known_unknown = 1
        elif "All Star" in g['home_team']:
            home_is_known_unknown = 1
        
        if g.get('away_team') is None:
            
            away_is_known_unknown = 1
        elif "ECLL" in g['away_team']:
            away_is_known_unknown = 1
        elif "Chapel Hill Rec" in g['away_team']:
            away_is_known_unknown = 1
        elif "All Star" in g['away_team']:
            away_is_known_unknown = 1
            
        g['missing_coaches'] = 0
        if g['found_in_assignr'] and None in [home_coaches, away_coaches]:
            
            err_msg = None
            if away_is_known_unknown and home_is_known_unknown:
                g['missing_coaches'] = 1
                err_msg = None # If we know that we aren't going to find coach names associated with the teams in question, then there is no reason to send an alert
            elif home_coaches is None and away_coaches is None:
                g['missing_coaches'] = 1
                err_msg = "[SDLL WARNING] Coaches not found for either team in game ID %d (%s vs %s)" % (g['game_ID'], g['home_team'], g['away_team'])
            elif (not home_is_known_unknown and home_coaches is None) and away_coaches is not None:
                g['missing_coaches'] = 1
                err_msg = "[SDLL WARNING] Coaches not found for %s in game ID %d (%s vs %s)" % (g['home_team'], g['game_ID'], g['home_team'], g['away_team'])
            elif home_coaches is not None and (not away_is_known_unknown and away_coaches is None):
                g['missing_coaches'] = 1
                err_msg = "[SDLL WARNING] Coaches not found for %s in game ID %d (%s vs %s)" % (g['away_team'], g['game_ID'], g['home_team'], g['away_team'])
            if err_msg is not None:
                print(err_msg)
                laxref.telegram_alert(err_msg)
    
    games_with_sent_email_records = [z for z in games if z['email_sent']]
    print ("Games with sent email records")
    zc.print_table(games_with_sent_email_records, {'keep_keys': ['away_team', 'no_umpire_assigned', 'home_team', 'game_date', 'location', 'league']})
    games = [z for z in games if not z['email_sent']]
    
    #games = [z for z in games if not z['missing_coaches']]
    
    games = [z for z in games if not (z.get('no_umpire_assigned') == 1)]
    
    games = [z for z in games if z['found_in_assignr']]
    print ("Games to send")
    zc.print_table(games, {'keep_keys': ['away_team', 'home_team', 'game_date', 'location', 'league']})
    
        
    for ig, game in enumerate(games):    
        print ("Game %d/%d" % (ig+1, len(games)))
        
        _html_send_umpire_day_of_email(game, EMAIL_TYPE)
        
        
            
    zc.exit("DONE EMAIL SENDS")
    
ALERTS = {}
def read_master_schedule():
    print('--read-master-schedule')
    
    if datetime.now().strftime("%Y%m%d") == "20260414":
        zc.exit("Wait until tomorrow")
    year = datetime.now().year
    misc = {}
    
    cursor = zc.zcursor("SDLL")
    
    query = "Select assignr_id from SDLL_Games where not ISNULL(assignr_id) and active group by assignr_id having count(1) > 1;"
    multiple_game_assignr_ids = cursor.dqr(query, [])
    if len(multiple_game_assignr_ids) > 0:
        
        msg = "[FATAL - FIX BEFORE ANYTHING ELSE]\n\nThere are multiple games in SDLL_Games that have the same assignr_id; this cannot happen and must be fixed\n{}\n\n{}".format("\n".join(map(str, [z['assignr_id'] for z in multiple_game_assignr_ids])), zc.get_original_script_command())
        laxref.telegram_alert(msg)
        zc.send_crash(msg)
        zc.exit("MULTIPLE GAMES w/ same assignr_id")
    
    
    local_query = "SELECT IFNULL(max(ID), 0)+1 next_game_ID from SDLL_Games fds;"
    next_game_ID = cursor.dqr(local_query, [])[0]['next_game_ID']
    misc['alternate_names'] = cursor.dqr("SELECT a.ID, a.team_ID, a.alternate_name, b.display_name actual_name from SDLL_Alternate_Team_Names a, SDLL_Team_Seasons b where b.is_spring=%s and b.active and a.team_ID=b.team_ID and a.year=b.year and a.active and a.year=%s;", [IS_SPRING, year])
    cursor.close()
    
    
    misc, service = read_from_google_sheet("all_games_master_doc", misc, {})
    misc, service = read_from_google_sheet("teamKey", misc, {})
    misc = convert_master_sheet_data_to_games(misc, service, {'version': 1})
    
    dir_path = os.path.join(sdll_fldr, 'Logs', 'MasterGamesArchive')
    
    mostRecentGames_txt = open(os.path.join(dir_path, 'lastGamesRead.json'), 'r').read()
    currentGames_txt = json.dumps(misc['doc_games'], default=zc.json_handler, indent=1)
    
    # No need for this since there may be changes to the sheet that do not reflect a change that we care about (teams,time,date,location)
    #if mostRecentGames_txt != currentGames_txt and '-quiet' not in sys.argv: 
    #    laxref.telegram_alert("[SDLL ALERT]\n\nA change has been made to the masterGames Sheet!!!")
    
    
    
    f = open(os.path.join(dir_path, 'lastGamesRead.json'), 'w')
    f.write(currentGames_txt)
    f.close()
    
    f = open(os.path.join(dir_path, 'masterGames%s.json' % datetime.now().strftime("%Y%m%d%H%M%S")), 'w')
    f.write(currentGames_txt)
    f.close()
    
    tmp_list_ = [z for z in misc['doc_games'] if "BB AA - Cubs" in [z['home_team'], z['away_team']]]
    if tmp_list_ != []:
        print ("\n AA Cubs games")
        zc.print_table(tmp_list_, {'keep_keys': ['source_row', 'game_date', 'home_team', 'away_team', 'league', 'location']})
    tmp_list_ = [z for z in misc['doc_games'] if z['league'] == "All Stars"][0:20]
    if tmp_list_ != []:
        print ("\n All Stars games/scrimmages")
        zc.print_table(tmp_list_, {'keep_keys': ['source_row', 'game_date', 'home_team', 'away_team', 'league', 'game_type', 'location']})
    unique_teams = [{'display_name': y, 'hashed_display_name': laxref.hash_player_name(str(y), {'keep_numbers': 1})} for y in list(set([z['home_team'] for z in misc['doc_games']] + [z['away_team'] for z in misc['doc_games']])) if y.endswith("U Orange") or y.endswith("U Green") or y.startswith("BB ") or y.startswith("SB ") or y.startswith("UMP -") or y.startswith("Cactus") or y.startswith("Grapefruit") or y.startswith("Intermediate") or y.startswith("LMP -") or y.startswith("Majors -") or y.startswith("Rookie -") or y.startswith("Juniors -") or y.startswith("Tee Ball -") or y.startswith("BB Tee Ball -") or y.startswith("AA -") or y.startswith("AAA -") or y.startswith("A -")]
    
    misc['doc_games_by_team'] = defaultdict(list)
    misc['doc_games_by_team_name'] = defaultdict(list)
    misc['db_games_by_team'] = defaultdict(list)
    for t in unique_teams:
        tmp_matches = [z['source_row'] for z in misc['doc_games'] if t['display_name'] in [z['home_team'], z['away_team']]]
        t['first_row'] = min(tmp_matches)
        t['times_seen'] = len(tmp_matches)
        
    # Remove blanks and TBDs
    ignore_names = []
    hashed_ignore_names = [laxref.hash_player_name(str(y), {'keep_numbers': 1}) for y in ignore_names]
    unique_teams = [z for z in unique_teams if z['hashed_display_name'] not in hashed_ignore_names]
    
    for t in unique_teams:
        t['n_games'] = len([1 for z in misc['doc_games'] if z['status'] != "cancelled" and t['hashed_display_name'] in [z['hashed_home_team'], z['hashed_away_team']]])
    # Assign Leagues
    for t in unique_teams:
        t['league'] = None
        if t['display_name'].startswith( "SB Minors" ):
            t['league'] = "SB Minors"
        elif t['display_name'].startswith( "BB Tee Ball" ) or t['display_name'].startswith( "Tee Ball - " ):
            t['league'] = "BB Tee Ball"
        elif t['display_name'].startswith( "SB Tee Ball" ):
            t['league'] = "SB Tee Ball"
        elif t['display_name'].startswith( "SB Rookie" ):
            t['league'] = "SB Rookie"
        elif t['display_name'].startswith( "SB Seniors" ):
            t['league'] = "SB Seniors"
        elif t['display_name'].startswith( "SB Majors" ):
            t['league'] = "SB Majors"
        elif t['display_name'].startswith( "Rookie - " ) or t['display_name'].startswith( "BB Rookie" ) or t['display_name'].startswith( "LMP -" ):
            t['league'] = "BB Rookie"
        elif t['display_name'].startswith( "BB Intermediate" ) or t['display_name'].startswith( "Intermediate" ):
            t['league'] = "BB Intermediate"
        elif t['display_name'].startswith( "BB Majors" ) or t['display_name'].startswith( "Majors - " ):
            t['league'] = "BB Majors"
        elif t['display_name'].startswith( "Juniors - " ):
            t['league'] = "BB Juniors"
        elif t['display_name'].startswith( "AAA - " ) or t['display_name'].startswith( "BB AAA" ) or t['display_name'].startswith( "Grapefruit" ):
            t['league'] = "BB AAA"
        elif t['display_name'].startswith( "AA - " ) or t['display_name'].startswith( "BB AA" ) or t['display_name'].startswith( "Cactus" ):
            t['league'] = "BB AA"
        elif t['display_name'].startswith( "A - " ) or t['display_name'].startswith( "BB A" ) or t['display_name'].startswith( "UMP -" ):
            t['league'] = "BB A"
        elif t['display_name'].endswith( "U Green" ):
            t['league'] = "All Stars"
        elif t['display_name'].endswith( "U Orange" ):
            t['league'] = "All Stars"
            
        
    unique_teams = sorted(unique_teams, key=lambda x:x['n_games'], reverse=True)

    #print ("\n\n Unique teams sorted by doc games")
    #zc.print_table(unique_teams)
    
    unique_leagues  = [{'league': z} for z in list(set([y['league'] for y in unique_teams]))]
    for l in unique_leagues:
        l['n_teams'] = len([1 for z in unique_teams if z['league'] == l['league']])
    unique_leagues.sort(key=lambda x:x['n_teams'], reverse=True)
    #print ("Unique Leagues\n------------------------------")
    #zc.print_table(unique_leagues)
    
    #print (f"Total games in capture: {(sum([z['n_games'] for z in unique_teams])/2):,}")
    #zc.exit("FDS")
    
    
    
    
    
    # Check whether the database needs to be updated
    cursor = zc.zcursor("SDLL")
    misc['db_games'] = cursor.dqr("SELECT ID, game_date, home_ID, away_ID, duration_in_hours duration, league, location, status, assignr_id, duration_in_hours, umpire_override, is_scrimmage from SDLL_Games where active and year=%s and is_spring=%s;", [year, IS_SPRING])
    misc['db_teams'] = {z['team_ID']: z for z in cursor.dqr("SELECT team_ID, display_name, league, IFNULL(is_placeholder, 0) is_placeholder FROM SDLL_Team_Seasons where active and year=%s and is_spring=%s;", [year, IS_SPRING])}
    
    cursor.close()
    
    
    for t in misc['db_teams'].values():
        t['alternate_names'] = [z for z in misc['alternate_names'] if z['team_ID'] == t['team_ID']]
  
    for g in misc['db_games']:
        g['is_a_reschedule'] = 0
        g['is_newly_created'] = 0
        g['tup'] = (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d%H"))
        g['tup_w_location'] = (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d%H"), g['location'])
        g['tup_w_only_location'] = (g['game_date'].strftime("%Y%m%d%H"), g['location'])
        g['tup_w_only_location_and_league'] = (g['game_date'].strftime("%Y%m%d%H"), g['location'], g['league'])
        g['tup_w_only_location_and_league_date_only'] = (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d"), g['location'], g['league'])
        g['tup_w_only_league_date_only'] = (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d"), g['league'])
        g['orig_location'] = g['location']
        g['orig_game_date'] = g['game_date']
        g['orig_home_ID'] = g['home_ID']
        g['orig_away_ID'] = g['away_ID']
        g['orig_league'] = g['league']
        g['orig_duration'] = g['duration']
        misc['db_games_by_team'][g['home_ID']].append(g)
        misc['db_games_by_team'][g['away_ID']].append(g)
        
        
        g['home_only_tup'] = (g['home_ID'], None, g['game_date'].strftime("%Y%m%d%H"))
        g['away_only_tup'] = (None, g['away_ID'], g['game_date'].strftime("%Y%m%d%H"))
        g['teams_only_tup'] = (g['home_ID'], g['away_ID'])
        g['alt_teams_only_tup'] = (g['away_ID'], g['home_ID'])
        g['home_only_tup_w_location'] = (g['home_ID'], None, g['game_date'].strftime("%Y%m%d%H"), g['location'])
        g['away_only_tup_w_location'] = (None, g['away_ID'], g['game_date'].strftime("%Y%m%d%H"), g['location'])
        g['teams_only_tup_w_location'] = (g['home_ID'], g['away_ID'], g['location'])
        g['alt_teams_only_tup_w_location'] = (g['away_ID'], g['home_ID'], g['location'])
        g['found_on_master'] = 0
        g['doc_activity'] = None
    
        g['home_is_placeholder'] = 0
        g['away_is_placeholder'] = 0
        tmp_home = "???"
        tmp_away = "???"
        if g['home_ID'] is not None:
            tmp_rec = misc['db_teams'].get(g['home_ID']) 
            if tmp_rec is not None:
                g['home_is_placeholder'] = tmp_rec['is_placeholder']
                tmp_home = tmp_rec['display_name']
        if g['away_ID'] is not None:
            tmp_rec = misc['db_teams'].get(g['away_ID']) 
            if tmp_rec is not None:
                g['away_is_placeholder'] = tmp_rec['is_placeholder']
                tmp_away = tmp_rec['display_name']
        
        g['both_are_placeholders'] = 1 if g['home_is_placeholder'] and g['away_is_placeholder'] else 0
        
        g['game_desc'] =  "%s %s (ID %s) vs %s (ID %s) @ %s" % (g['game_date'].strftime("%Y%m%d"), tmp_home, g['home_ID'], tmp_away, g['away_ID'], g['location'])
        
    for g in misc['db_teams'].values():
        g['hashed_display_name'] = laxref.hash_player_name(str(g['display_name']), {'keep_numbers': 1})
        g['tup'] = (g['hashed_display_name'], clean_league_name(g['league']))
        
        g['n_games'] = len(misc['db_games_by_team'][g['team_ID']])
        g['coach_emails'] = misc['coaches_by_team_display_name'].get(g['display_name'])
    
    print ("\n\n Unique teams sorted by db games")
    tmp_list_ = sorted(misc['db_teams'].values(), key=lambda x:x['n_games'], reverse=True)
    zc.print_table(tmp_list_, {'keep_keys': ['display_name', 'n_games']})
    
    ###################################
    # Add home/away IDs to the game records from the doc
    ###################################
    
    # Prep game records
    for g in misc['doc_games']:
        g['home_ID'] = None; g['away_ID'] = None; g['a_team_was_identified'] = 0
        g['home_is_TBD'] = 0; g['away_is_TBD'] = 0
        g['home_is_placeholder'] = 0; g['away_is_placeholder'] = 0
        g['home_tup'] = (g['hashed_home_team'], clean_league_name(g['league']))
        g['away_tup'] = (g['hashed_away_team'], clean_league_name(g['league']))
        
    zc.print_table(list(misc['db_teams'].values()))
    print (f"^ misc.db_teams ({len(misc['db_teams'])})")
    #zc.exit("DB T")
    
    league_name_teams_hashMap = {z['tup']: z for z in misc['db_teams'].values()}
    #pprint (league_name_teams_hashMap)
    #zc.exit("FDS")
    
    # Prep game records
    for g in misc['doc_games']:
            
        if g['home_team'] in ["TBD", ""] or is_TBD(g['home_team']):
            g['home_is_TBD'] = 1
        else:
            
            if g['game_type'] in ['Scrimmage', "Game", 'EOST']:
                misc['doc_games_by_team_name'][g['home_team']].append(g)
            tmp_rec = league_name_teams_hashMap.get(g['home_tup']) 
            #print ("tup: %s" % str(g['home_tup']))
            if tmp_rec is not None:
                g['home_ID'] = tmp_rec['team_ID']
                misc['doc_games_by_team'][g['home_ID']].append(g)
                g['home_is_placeholder'] = tmp_rec['is_placeholder']
                g['a_team_was_identified'] = 1
            
        if g['away_team'] in ["TBD", ""] or is_TBD(g['away_team']):
            g['away_is_TBD'] = 1
        else:
            if g['game_type'] in ['Scrimmage', "Game", 'EOST']:
                misc['doc_games_by_team_name'][g['away_team']].append(g)
            tmp_rec = league_name_teams_hashMap.get(g['away_tup'])
            if tmp_rec is not None:
                g['away_ID'] = tmp_rec['team_ID']
                misc['doc_games_by_team'][g['away_ID']].append(g)
                g['away_is_placeholder'] = tmp_rec['is_placeholder']
                g['a_team_was_identified'] = 1
        
        g['both_are_placeholders'] = 1 if g['away_is_placeholder'] and g['home_is_placeholder'] else 0
        
        if not g['both_are_placeholders'] and g['game_type'] == "EOST" and g['home_is_TBD'] and g['away_is_TBD']:
            g['both_are_placeholders'] = 1
        
           
    #print ("\n\n 10/17 Doc Games")
    #zc.print_table([z for z in misc['doc_games'] if z['league'] == "SB Rookie" and z['game_date'].strftime("%Y%m%d") == "20251017"], {'keep_keys': ['location', 'league', 'away_team', 'home_team', 'away_ID', 'home_ID', 'game_date', 'a_team_was_identified', 'status']})
    #zc.exit("10/17")
            
    if '--print-doc-games' in sys.argv:
        tmp_list = [z for z in misc['doc_games'] if z['league'] not in ['Tee Ball'] and z['league'] == "BB AA"]
        zc.print_table(tmp_list, {'cutoff*': 20, 'keep_keys': "source_row                    game_date                                                        home_team                     away_team                     league                        location                                               game_type                     status                        db_game_ID                                                                                             home_ID                       away_ID                                home_is_TBD                   away_is_TBD                   home_is_placeholder           away_is_placeholder                 umpire_override                                      "})
        print ("\n    nTotal=%d" % len(tmp_list))
        print ("    nGames=%d" % len([z for z in tmp_list if z['game_type'] == "Game"]))
        print ("nScrimmage=%d" % len([z for z in tmp_list if z['game_type'] == "Scrimmage"]))
        zc.exit("DOC GAMES")
        
    
    
    # See if the unique teams are in the DB; if not add them
    params = []
    unidentified_teams = []
    new_team_queries = []
    name_update_queries = []
    new_alternate_name_queries = []
    for t in unique_teams:
        tup = (t['hashed_display_name'], t['league'])
        
        #if tup not in [z['tup'] for z in misc['db_teams'].values()]:
        if league_name_teams_hashMap.get(tup) is None:
           
            if not t['display_name'].endswith("- TBD"):
                
                query = "INSERT INTO SDLL_Team_Seasons (active, year, league, display_name, is_spring) VALUES (%s, %s, %s, %s, %s);"
                param = [1, year, t['league'], t['display_name'], IS_SPRING]
                params.append(param)
                unidentified_teams.append("%s (%s; firstRow=%d; timesSeen=%d)"% ( t['display_name'], t['league'], t['first_row'], t['times_seen']))
                new_team_query = "INSERT INTO SDLL_Team_Seasons (active, year, display_name, league, is_spring) VALUES (1, {}, '{}', '{}', {});".format(
                    datetime.now().year
                    , t['display_name'].replace("'", "''"), t['league'], IS_SPRING
                )
                new_team_queries.append(new_team_query)
                #print (new_team_query)
                
                # Check if the new teams share a large number of games with teams that are no longer showing up
                print (new_team_query)
                #print ("DB teams")
                #print ("\n".join([z['display_name'] for z in misc['db_teams'].values()]))
                #print("Found: %s" % (t['display_name'] in [z['display_name'] for z in misc['db_teams'].values()]))
                
                new_team_games = misc['doc_games_by_team_name'][t['display_name']]
                n_new_team_games = len(new_team_games)
                opponents = {}
                for ng in new_team_games:
                    ng['match_tup'] = (ng['game_date'].strftime("%Y%m%d%H%M"), ng['location'])
                    if ng['home_team'] == t['display_name']:
                        opponents[ng['away_team']] = opponents.get(ng['away_team'], 0) + 1
                    elif ng['away_team'] == t['display_name']:
                        opponents[ng['home_team']] = opponents.get(ng['home_team'], 0) + 1
                print ("\n\n Doc games for %s" % (t['display_name']))
                zc.print_table(new_team_games, {'keep_keys': ['game_date', 'source_row', 'home_team', 'away_team', 'location']})
                
                potential_renaming_candidates = []
                # Now cycle through all the teams in the database to see how many games 
                for potential_match in misc['db_teams'].values():
                    n_matches = 0
                    n_total = 0
                    for g in misc['db_games_by_team'][potential_match['team_ID']]:
                        
                        
                        g['match_tup'] = (g['game_date'].strftime("%Y%m%d%H%M"), g['location'])
                        n_total += 1
                        home_team = misc['db_teams'].get(g['home_ID'])
                        away_team = misc['db_teams'].get(g['away_ID'])
                   
                        if g['match_tup'] in [z['match_tup'] for z in new_team_games]: # check that the date/locations match
                            # Now if our "new" team has a game against this potential team, it's unlikely that it's a renaming
                            if opponents.get(potential_match['display_name']) is None:
                                n_matches += 1
                                

                    d = {'team_ID': potential_match['team_ID'], 'display_name': potential_match['display_name']
                    , 'n_total_games': n_total, 'n_matching_games': n_matches
                    }
                    if n_matches > 0 and n_matches == n_total:
                        
                        d['exp'] = f"ALERT!!! Of the {n_new_team_games} games {t['display_name']} has on the Master sheet, all match to database records associated with {potential_match['display_name']}; there is a good chance that this is a renamed team"
                        name_change_query = f"UPDATE SDLL_Team_Seasons set display_name=\'{t['display_name']}\' where team_ID={potential_match['team_ID']};"
                        print (name_change_query)
                        name_update_queries.append(name_change_query + "# {}".format(d['exp']))
                    else:
                        d['exp'] = f"Of the {n_new_team_games} games {t['display_name']} has on the Master sheet, {n_matches} match to database records associated with {potential_match['display_name']}; unlikely to be a match"
                    potential_renaming_candidates.append(d)
                potential_renaming_candidates = sorted(potential_renaming_candidates, key=lambda x:x['n_matching_games'], reverse=True)
                zc.print_table([z for z in potential_renaming_candidates if z['n_matching_games'] > 0], {'cutoff4': 100})
                
                #zc.exit("FSD")
                
                
                alternate_name_query = "INSERT INTO SDLL_Alternate_Team_Names (active, team_ID, alternate_name, league, year) VALUES (1, #, '{}', '{}', {});".format(t['display_name'].replace("'", "''"), t['league'], datetime.now().year)
                new_alternate_name_queries.append (alternate_name_query)
    if len(new_alternate_name_queries) > 0:
        print ("\n New Team Queries (n=%d)\n" % len(new_team_queries))
        print ("\n".join(new_team_queries))
        print ("\n Name Update Queries (n=%d)\n" % len(name_update_queries))
        print ("\n".join(name_update_queries))
        print ("\n New Alternate Name Queries\n")
        print ("\n".join(new_alternate_name_queries))
        laxref.telegram_alert("[SDLL UNKNOWN TEAMS]\n\nThere were %d team names that were not recognized. Most commonly, this means that a placeholder has been replaced with the actual name or it's the initial load." % (len(new_alternate_name_queries)))
        
        f = open(os.path.join(sdll_fldr, "Logs", "SDLL_name_update_queries.sql"), 'w')
        f.write("# This script contains all the team names that seem to reflect a placeholder having been replaced with an actual name\n\n")
        f.write("\n".join(name_update_queries))
        f.close()
        f = open(os.path.join(sdll_fldr, "Logs", "SDLL_alternate_name_queries.sql"), 'w')
        f.write("# This script contains all the team names that seem to reflect a placeholder having been replaced with an actual name\n\n")
        f.write("\n".join(new_alternate_name_queries))
        f.close()
        
    if '--just-print-team-seasons' in sys.argv:  
        zc.exit("TEAM S")        
    if '--see-alternate-name-queries' in sys.argv:
        
        zc.exit("ALT NAMES")
    if '--add-team-seasons' in sys.argv:
        if len(params) > 0:
            cursor = zc.zcursor("SDLL")
            cursor.executemany(query, params)
            cursor.commit()
            cursor.close()
    else:
        if len(params) > 0 and '-quiet' not in sys.argv and '--update-assignr-games' not in sys.argv:
            unidentified_teams_list = "\n".join(unidentified_teams)
            msg = (f"There are {len(params)} unidentified teams in the master games doc\n\n{unidentified_teams_list}")
            if datetime.now().strftime("%Y%m%d") != "20260413":
                laxref.telegram_alert("[SDLL WARNING]\n\n{}\n\n{}".format(msg, zc.get_original_script_command()))
            print (msg)
            
    
    # For active (i.e. non-cancelled) games with at least one team identified, check if a record exists in the DB for the combination of team and date
    queries = []; params = []
    db_updates = []
    new_game_IDs = [] # the IDs set aside for new game records (if these game IDs would trigger a location change or a time change, do not display it because it will be taken care of with the record insertion; in other words, there is no existing record to update)
    for g in misc['doc_games']:
        g['tup_w_only_location'] = (g['game_date'].strftime("%Y%m%d%H"), g['location'])
        g['tup_w_only_location_and_league'] = (g['game_date'].strftime("%Y%m%d%H"), g['location'], g['league'])
        g['tup_w_only_location_and_league_date_only'] = (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d"), g['location'], g['league'])
        g['tup_w_only_league_date_only'] = (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d"), g['league'])
        g['tup'] = (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d%H"))
        g['tup_w_location'] = (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d%H"), g['location'])
        g['switched_tup'] = (g['away_ID'], g['home_ID'], g['game_date'].strftime("%Y%m%d%H"))
        g['game_desc'] = "%s %s (ID %s) vs %s (ID %s)" % (g['game_date'].strftime("%Y%m%d"), g['home_team'], g['home_ID'], g['away_team'], g['away_ID'])
        
    ID_update_types = {'missing_and_added': 0, 'correct': 0, 'incorrect': 0}
    ID_update_types_incorrect_rows = []
    ID_update_types_incorrect_records = []
    doc_games_by_row_hashMap = {z['source_row']: z for z in misc['doc_games']}
    db_games_hashMap = {z['ID']: z for z in misc['db_games']}
    
    # Go through all the games from the master doc and try to match to a database game
    for g in misc['doc_games']:
        #if g['game_type'] == "Rainout": continue
        g['is_scrimmage'] = 1 if laxref.hash_player_name(g['game_type']) in ['scrimmage'] else 0
        #zc.print_dict_as_table(g); zc.exit("G")
        check1 = g['a_team_was_identified']
        check2 = g['game_type'] == "EOST" and g['both_are_placeholders']
        check3 = not g['status'] in ['cancelled']
        if (check1 or check2) and check3:
                
            # THere was an issue where the BCLL teams were all set to play a generic BB Majors team (which was causing multiple rows to match for a given date)
            
            tmp_rec = None # Only populated if we find a match in the DB
            tmp_rec_match_code = None
            n_matches = None
            same_league_location_time_check = g['tup_w_only_location_and_league'] in [z['tup_w_only_location_and_league'] for z in misc['db_games']]
            local_tmp_rec = None
            if same_league_location_time_check:
                local_tmp_rec =  misc['db_games'][ [z['tup_w_only_location_and_league'] for z in misc['db_games']].index(g['tup_w_only_location_and_league']) ]
            same_league_location_date_but_not_time_check = g['tup_w_only_location_and_league_date_only'] in [z['tup_w_only_location_and_league_date_only'] for z in misc['db_games']]
            local_tmp_rec_date_not_time = None
            if same_league_location_date_but_not_time_check:
                local_tmp_rec_date_not_time =  misc['db_games'][ [z['tup_w_only_location_and_league_date_only'] for z in misc['db_games']].index(g['tup_w_only_location_and_league_date_only']) ]
            
            same_league_teams_date_but_not_time_check = g['tup_w_only_league_date_only'] in [z['tup_w_only_league_date_only'] for z in misc['db_games']] and g['tup'] not in [z['tup'] for z in misc['db_games']]
            local_tmp_rec_teams_and_date_but_not_time = None
            if same_league_teams_date_but_not_time_check: # This was a game where the teams were playing on a certain date, but the time and location was different (it wasn't being flagged as a location/time change, but it should have been)
                local_tmp_rec_teams_and_date_but_not_time =  misc['db_games'][ [z['tup_w_only_league_date_only'] for z in misc['db_games']].index(g['tup_w_only_league_date_only']) ]
            
            
            
            if 0 and g['source_row'] == 2174:
                zc.print_dict_as_table(g)
                
                print ("Check 1: %s" % (same_league_location_time_check))
                print ("Check 2: %s" % (same_league_location_date_but_not_time_check))
                print ("Check 3: %s" % (same_league_teams_date_but_not_time_check))
                if same_league_location_time_check:
                    zc.print_dict_as_table(local_tmp_rec)
                if same_league_location_date_but_not_time_check:
                    zc.print_dict_as_table(local_tmp_rec_date_not_time)
                if same_league_teams_date_but_not_time_check:
                    zc.print_dict_as_table(local_tmp_rec_teams_and_date_but_not_time)
                
                input ("855 - PD")
                
            # The game is likely a location OR time change because the teams are the same and the date are the same, but the location OR time are different
            if 0 and (not g['both_are_placeholders'] and same_league_location_time_check and ('both_are_placeholders' in local_tmp_rec and local_tmp_rec['both_are_placeholders']) and None not in [g['home_ID'], g['away_ID']]): # We have a record with the home team played TBD; update?
                tmp_rec =  misc['db_games'][ [z['tup_w_only_location_and_league'] for z in misc['db_games']].index(g['tup_w_only_location_and_league']) ]
                tmp_rec_match_code = "Both Team IDs added"

                        
                query = "UPDATE SDLL_Games set away_ID=%s, home_ID=%s where ID=%s;"
                param = [g['away_ID'], g['home_ID'], tmp_rec['ID']]
                #queries.append(query); params.append(param)
                tmp_rec['away_ID'] = g['away_ID']
                tmp_rec['home_ID'] = g['home_ID']
                
                update = {'db_game_ID': tmp_rec['ID'], 'game_date': g['game_date'], 'game_type': g['game_type'], 'league': tmp_rec['league'], 'proposed_query': query, 'proposed_param': param, 'tup_w_only_location_and_league': g['tup_w_only_location_and_league'], 'src_row': g['source_row'], 'seq': len(db_updates) + 1, 'tag': 'both_team_IDs', 'game_desc': "{} {} vs {} @ {}".format(g['game_date'].strftime("%Y%m%d"), g['home_team'], g['away_team'], g['location']), 'desc': 'Team IDs', 'field': 'team_IDs', 'from': "%s/%s" % (tmp_rec['home_ID'], tmp_rec['away_ID']), 'to': "%s/%s" % (g['home_ID'], g['away_ID']), 'home_ID': g['home_ID'], 'away_ID': g['away_ID']}
                db_updates.append(update)
                #zc.print_dict(update)
                #zc.exit("UPD")
                
            
            elif 1 and (g['both_are_placeholders'] and same_league_location_time_check and ('both_are_placeholders' in local_tmp_rec and not local_tmp_rec['both_are_placeholders']) and None in [local_tmp_rec['home_ID'], local_tmp_rec['away_ID']] and None not in [g['home_ID'], g['away_ID']]): # We have a record with the home team played TBD; update?
                tmp_rec =  misc['db_games'][ [z['tup_w_only_location_and_league'] for z in misc['db_games']].index(g['tup_w_only_location_and_league']) ]
                tmp_rec_match_code = "Both Team IDs added"

                        
                query = "UPDATE SDLL_Games set away_ID=%s, home_ID=%s where ID=%s;"
                param = [g['away_ID'], g['home_ID'], tmp_rec['ID']]
                #queries.append(query); params.append(param)
                update = {'db_game_ID': tmp_rec['ID'], 'game_date': g['game_date'], 'game_type': g['game_type'], 'league': tmp_rec['league'], 'proposed_query': query, 'proposed_param': param, 'tup_w_only_location_and_league': g['tup_w_only_location_and_league'], 'src_row': g['source_row'], 'seq': len(db_updates) + 1, 'tag': 'both_team_IDs', 'game_desc': "{} {} vs {} @ {}".format(g['game_date'].strftime("%Y%m%d"), g['home_team'], g['away_team'], g['location']), 'desc': 'Team IDs', 'field': 'team_IDs', 'from': "%s/%s" % (tmp_rec['home_ID'], tmp_rec['away_ID']), 'to': "%s/%s" % (g['home_ID'], g['away_ID']), 'home_ID': g['home_ID'], 'away_ID': g['away_ID']}
                tmp_rec['away_ID'] = g['away_ID']
                tmp_rec['home_ID'] = g['home_ID']
                
                db_updates.append(update)
                #zc.print_dict_as_table(update)
                #zc.exit("UPD")
                
            
            elif not g['both_are_placeholders'] and same_league_teams_date_but_not_time_check and ('both_are_placeholders' not in local_tmp_rec_teams_and_date_but_not_time or not local_tmp_rec_teams_and_date_but_not_time['both_are_placeholders']) and None not in [g['home_ID'], g['away_ID']]: # We have a record with where the teams and the date are the same, but the location OR the time have changed
                tmp_rec =  misc['db_games'][ [z['tup_w_only_league_date_only'] for z in misc['db_games']].index(g['tup_w_only_league_date_only']) ]
                update = {'db_game_ID': tmp_rec['ID'], 'game_type': g['game_type'], 'league': tmp_rec['league'], 'proposed_query': None, 'proposed_param': None, 'tup_w_only_location_and_league': g['tup_w_only_location_and_league'], 'src_row': g['source_row'], 'seq': len(db_updates) + 1, 'tag': None, 'game_desc': "{} {} vs {} @ {}".format(g['game_date'].strftime("%Y%m%d"), g['home_team'], g['away_team'], g['location']), 'desc': 'Time Change Only', 'field': 'game_date', 'from': tmp_rec['game_date'], 'to': g['game_date']}
                if g['location'] != local_tmp_rec_teams_and_date_but_not_time['location'] and g['game_date'] != local_tmp_rec_teams_and_date_but_not_time['game_date']:
                    tmp_rec_match_code = "Time & location change"
                    tmp_rec['found_on_master'] = 1
                    tmp_rec['doc_activity'] = g['game_type']

                        
                    query = "UPDATE SDLL_Games set game_date=%s, location=%s where ID=%s;"
                    param = [g['game_date'], g['location'], tmp_rec['ID']]
                    update['proposed_query'] = query; update['proposed_param'] = param
                    update['tag'] = "Time & Location Change"
                    update['desc'] = "Time & Location Change"
                    update['location'] = g['location']
                    update['game_date'] = g['game_date']
                    tmp_rec['game_date'] = g['game_date']
                    tmp_rec['location'] = g['location']
                elif g['location'] == local_tmp_rec_teams_and_date_but_not_time['location'] and g['game_date'] != local_tmp_rec_teams_and_date_but_not_time['game_date']:
                    tmp_rec_match_code = "Time & location change"
                    tmp_rec['found_on_master'] = 1
                    tmp_rec['doc_activity'] = g['game_type']

                        
                    query = "UPDATE SDLL_Games set game_date=%s where ID=%s;"
                    param = [g['game_date'], tmp_rec['ID']]
                    update['proposed_query'] = query; update['proposed_param'] = param
                    update['tag'] = "Time change"
                    update['desc'] = "Time Change Only"
                    update['game_date'] = g['game_date']
                    tmp_rec['game_date'] = g['game_date']
                elif g['location'] != local_tmp_rec_teams_and_date_but_not_time['location'] and g['game_date'] == local_tmp_rec_teams_and_date_but_not_time['game_date']:
                    
                    tmp_rec_match_code = "Location change"
                    tmp_rec['found_on_master'] = 1
                    tmp_rec['doc_activity'] = g['game_type']
                    tmp_rec['doc_activity'] = g['game_type']

                        
                    query = "UPDATE SDLL_Games set location=%s where ID=%s;"
                    param = [g['location'], tmp_rec['ID']]
                    update['proposed_query'] = query; update['proposed_param'] = param
                    update['tag'] = "Location change"
                    update['desc'] = "Location Change Only"
                    update['location'] = g['location']
                    tmp_rec['location'] = g['location']
                    
                db_updates.append(update)
                
                    
                
            # The game is likely just a time change because the teams are the same, the location and league are the same and the date is the same; the only thing different is the time of the game
            elif not g['both_are_placeholders'] and same_league_location_date_but_not_time_check and ('both_are_placeholders' not in local_tmp_rec_date_not_time or not local_tmp_rec_date_not_time['both_are_placeholders']) and None not in [g['home_ID'], g['away_ID']] and g['game_date'] != local_tmp_rec_date_not_time['game_date']: # We have a record with where everything is the same except the time has changed
                tmp_rec =  misc['db_games'][ [z['tup_w_only_location_and_league_date_only'] for z in misc['db_games']].index(g['tup_w_only_location_and_league_date_only']) ]
                tmp_rec_match_code = "Time change"
                tmp_rec['found_on_master'] = 1
                tmp_rec['doc_activity'] = g['game_type']

                        
                query = "UPDATE SDLL_Games set game_date=%s where ID=%s;"
                param = [g['game_date'], tmp_rec['ID']]
                #queries.append(query); params.append(param)
                
                update = {'db_game_ID': tmp_rec['ID'], 'game_type': g['game_type'], 'league': tmp_rec['league'], 'proposed_query': query, 'proposed_param': param, 'tup_w_only_location_and_league': g['tup_w_only_location_and_league'], 'src_row': g['source_row'], 'seq': len(db_updates) + 1, 'tag': 'time_change', 'game_desc': "{} {} vs {} @ {}".format(g['game_date'].strftime("%Y%m%d"), g['home_team'], g['away_team'], g['location']), 'desc': 'Time Change Only', 'field': 'game_date', 'from': tmp_rec['game_date'], 'to': g['game_date']}
                db_updates.append(update)
                #zc.print_dict(update)
                #zc.exit("UPD")
                tmp_rec['game_date'] = g['game_date']
                
            elif not g['both_are_placeholders'] and same_league_location_time_check and ('both_are_placeholders' in local_tmp_rec and not local_tmp_rec['both_are_placeholders']) and None not in [g['home_ID'], g['away_ID']] and local_tmp_rec['home_ID'] is None and local_tmp_rec['away_ID'] == g['away_ID']: # We found a location and time match and the home team matches, but the away team a
                tmp_rec = [z for z in misc['db_games'] if z['tup_w_only_location_and_league'] == g['tup_w_only_location_and_league']]
                
                if len(tmp_rec) > 1:
                    laxref.telegram_alert("[SDLL ALERT!!!]\n\nThere are two teams in the DB matching to the same time at the same field. This should not happen!!!\n\n{}".format(zc.get_original_script_command()))
                    zc.send_crash("Same time/same field:\n\n{}".format(zc.print_table(tmp_rec)))
                    zc.exit("EXIT")
                else:
                    if 0 and g['source_row'] == 3112:
                        print(n_matches, n_matches_w_location)
                        zc.print_dict_as_table(tmp_rec)
                        zc.print_dict_as_table(g)
                        zc.exit("NM")
                    tmp_rec = tmp_rec[0]    
                    tmp_rec_match_code = "Home ID added / Away ID already present"
                    query = "UPDATE SDLL_Games set home_ID=%s where ID=%s;"
                    param = [g['home_ID'], tmp_rec['ID']]
                    #queries.append(query); params.append(param)
                    tmp_rec['home_ID'] = g['home_ID']
                    
                    if '--via-cron' not in sys.argv:
                        update = {'db_game_ID': tmp_rec['ID'], 'game_type': g['game_type'], 'league': tmp_rec['league'], 'proposed_query': query, 'proposed_param': param, 'tup_w_only_location_and_league': g['tup_w_only_location_and_league'], 'src_row': g['source_row'], 'seq': len(db_updates) + 1, 'tag': 'single_team_IDs', 'game_desc': "{} {} vs {} @ {}".format(g['game_date'].strftime("%Y%m%d"), g['home_team'], g['away_team'], g['location']), 'desc': 'Update Single Placeholder', 'field': 'team_IDs', 'from': "???", 'to': g['home_ID'], 'home_ID': g['home_ID'], 'away_ID': g['away_ID']}
                        
                        
                        print ("DB Game")
                        print (" {}".format(tmp_rec['game_desc']))
                        print ("Doc Game")
                        print (" {} @ {}".format(g['game_desc'], g['location']))
                        
                        print ("\nIt appears that the missing team has been identified on the Master sheet (source row=%d). Should we make the change to our DB too\n\nQuery: UPDATE SDLL_Games set home_ID=%s where ID=%s;" % (g['source_row'], g['home_ID'], tmp_rec['ID']))
                        if not ALERTS.get('approveAllMissingTeamUpdates'):
                            resp = input("\n\n To make the update, enter y or approve-all: ").strip().lower()
                        else:
                            resp = "approve-all"
                        if resp == "approve-all":
                            ALERTS['approveAllMissingTeamUpdates'] = 1
                        if ALERTS.get('approveAllMissingTeamUpdates') or resp == "y":
                            db_updates.append(update)
                    elif 'UPDATE TEAM ID' not in ALERTS:
                        ALERTS['UPDATE TEAM ID'] = 1
                        laxref.telegram_alert("[SDLL confirmation H]\n\nThere was a game in the DB that was missing a team ID; it looks like it's been added to the Master Sheet and we should make the update if we can confirm it")
                        
                    #zc.print_dict(update)
                    #zc.exit("UPD")
                    
            elif not g['both_are_placeholders'] and same_league_location_time_check and ('both_are_placeholders' in local_tmp_rec and not local_tmp_rec['both_are_placeholders']) and None not in [g['home_ID'], g['away_ID']] and local_tmp_rec['home_ID'] == g['home_ID'] and local_tmp_rec['away_ID'] is None: # We found a location and time match and the away team matches, but the home team a
                tmp_rec = [z for z in misc['db_games'] if z['tup_w_only_location_and_league'] == g['tup_w_only_location_and_league']]
                
                if len(tmp_rec) > 1:
                    laxref.telegram_alert("[SDLL ALERT!!!]\n\nThere are two teams in the DB matching to the same time at the same field. This should not happen!!!\n\n{}".format(zc.get_original_script_command()))
                    zc.send_crash("Same time/same field:\n\n{}".format(zc.print_table(tmp_rec)))
                    zc.exit("EXIT")
                else:
                    if 0 and g['source_row'] == 3112:
                        print(n_matches, n_matches_w_location)
                        zc.print_dict_as_table(tmp_rec)
                        zc.print_dict_as_table(g)
                        zc.exit("NM")
                    tmp_rec = tmp_rec[0]   
                    tmp_rec_match_code = "Away ID added / Home ID already present" 
                    query = "UPDATE SDLL_Games set away_ID=%s where ID=%s;"
                    param = [g['away_ID'], tmp_rec['ID']]
                    #queries.append(query); params.append(param)
                    tmp_rec['away_ID'] = g['away_ID']
                    
                    if '--via-cron' not in sys.argv:
                        update = {'db_game_ID': tmp_rec['ID'], 'game_type': g['game_type'], 'league': tmp_rec['league'], 'proposed_query': query, 'proposed_param': param, 'tup_w_only_location_and_league': g['tup_w_only_location_and_league'], 'src_row': g['source_row'], 'seq': len(db_updates) + 1, 'tag': 'single_team_IDs', 'game_desc': "{} {} vs {} @ {}".format(g['game_date'].strftime("%Y%m%d"), g['home_team'], g['away_team'], g['location']), 'desc': 'Update Single Placeholder', 'field': 'team_IDs', 'from': "???", 'to': g['away_ID'], 'home_ID': g['home_ID'], 'away_ID': g['away_ID']}
                        
                        
                        print ("DB Game")
                        print (" {}".format(tmp_rec['game_desc']))
                        print ("Doc Game")
                        print (" {} @ {}".format(g['game_desc'], g['location']))
                        
                        print ("\nIt appears that the missing team has been identified on the Master sheet. Should we make the change to our DB too\n\nQuery: UPDATE SDLL_Games set away_ID=%s where ID=%s;" % (g['away_ID'], tmp_rec['ID']))
                        if not ALERTS.get('approveAllMissingTeamUpdates'):
                            resp = input("\n\n To make the update, enter y or approve-all: ").strip().lower()
                        else:
                            resp = "approve-all"
                        if resp == "approve-all":
                            ALERTS['approveAllMissingTeamUpdates'] = 1
                        if ALERTS.get('approveAllMissingTeamUpdates') or resp == "y":
                            db_updates.append(update)
                            ALERTS['missingTeamsAdded'] = 1
                    elif 'UPDATE TEAM ID' not in ALERTS:
                        ALERTS['UPDATE TEAM ID'] = 1
                        laxref.telegram_alert("[SDLL confirmation A]\n\nThere was a game in the DB that was missing a team ID; it looks like it's been added to the Master Sheet and we should make the update if we can confirm it")
                        
                    #zc.print_dict(update)
                    #zc.exit("UPD")
                    
            elif g['tup_w_location'] in [z['tup_w_location'] for z in misc['db_games']]: # Already found with both teams 
                if g['both_are_placeholders']: # We need to check the location in addition to the date/teams 
                    n_matches_w_location = len([1 for z in misc['db_games'] if z['tup_w_location'] == g['tup_w_location']])
                    n_matches = len([1 for z in misc['db_games'] if z['tup'] == g['tup']])
                    
                    if n_matches >= 1 and n_matches_w_location == 1: # Single game with a single matching location
                        tmp_rec =  misc['db_games'][ [z['tup_w_location'] for z in misc['db_games']].index(g['tup_w_location']) ]
                        tmp_rec_match_code = "Dual Placeholders - 1 tup_w_location match"
                        tmp_rec['found_on_master'] = 1
                        tmp_rec['doc_activity'] = g['game_type']
                    elif n_matches >= 1 and n_matches_w_location == 0: # Single game between placeholders, but location is different
                        
                        query = "INSERT INTO SDLL_Games (active, game_date, home_ID, away_ID, league, location, status, year, date_added, duration_in_hours, is_spring, is_scrimmage) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)";
                        param = [1, g['game_date'], g['home_ID'], g['away_ID'], g['league'], g['location'], 'active', year, datetime.now(), g['duration_in_hours'], IS_SPRING, g['is_scrimmage']]
                        #queries.append(query); params.append(param)
                        if g['game_date'] <= datetime.now() and datetime.now() > datetime(2025, 6, 5):
                            if 'OLDGMALT' not in ALERTS and '-quiet' not in sys.argv and '--update-assignr-games' not in sys.argv:
                                ALERTS['OLDGMALT'] = 1
                                msg = "[WARNING.a] there was at least one game from the past that was found in the master sheet, but not in the DB"
                                print(msg)
                                laxref.telegram_alert(msg)
                        else:
                            if 'NEWALTLOC' not in ALERTS and '-quiet' not in sys.argv and '--update-assignr-games' not in sys.argv and '--via-cron' in sys.argv:
                                ALERTS['NEWALTLOC'] = 1
                                msg = f"[WARNING - NEW Game added] There was a game between two placeholder teams that was already found for a given date, but the location was different, which suggests it's actually a different game in the same league among different placeholder teams\n\n{json.dumps(g, default=zc.json_handler)}"
                                print(msg)
                                if datetime.now() > datetime(2026, 5, 26):
                                    laxref.telegram_alert(msg)
                                
                            g['game_desc'] =  "%s %s (ID %s) vs %s (ID %s) @ %s" % (g['game_date'].strftime("%Y%m%d"), g['home_team'], g['home_ID'], g['away_team'], g['away_ID'], g['location'])
                            
                            misc['db_games'].append({'ID': next_game_ID
                            , 'game_date': g['game_date']
                            , 'duration_in_hours': g['duration_in_hours']
                            , 'home_ID': g['home_ID']
                            , 'away_ID': g['away_ID']
                            , 'found_on_master': 1
                            , 'is_newly_created': 1
                            , 'assignr_id': None
                            , 'umpire_override': None
                            
                            , 'tup': (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d%H"))
                            , 'tup_w_location': (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d%H"), g['location'])
                            , 'tup_w_only_location': (g['game_date'].strftime("%Y%m%d%H"), g['location'])
                            , 'tup_w_only_location_and_league': (g['game_date'].strftime("%Y%m%d%H"), g['location'], g['league'])
                            , 'tup_w_only_location_and_league_date_only': (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d"), g['location'], g['league'])
                            , 'tup_w_only_league_date_only': (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d"), g['league'])
                            , 'home_only_tup': (g['home_ID'], None, g['game_date'].strftime("%Y%m%d%H"))
                            , 'away_only_tup': (None, g['away_ID'], g['game_date'].strftime("%Y%m%d%H"))
                            , 'game_desc': g['game_desc']
                            
                            , 'league': None if g['league'] is None else g['league'].strip()
                            , 'location': None if g['location'] is None else g['location'].strip()
                            , 'status': 'active'
                            , 'year': year
                            , 'is_scrimmage': 0 if g['game_type'] == "Scrimmage" else 1
                            })

                            tmp_db_home = None
                            tmp_db_away = None
                            if g['home_ID'] is not None:
                                tmp_db_home = misc['db_teams'].get(g['home_ID'])
                            if g['away_ID'] is not None:
                                tmp_db_away = misc['db_teams'].get(g['away_ID'])
                        
                            update = {'db_game_ID': next_game_ID, 'game_type': g['game_type'], 'league': g['league'], 'proposed_query': query, 'proposed_param': param, 'tup_w_only_location_and_league': g['tup_w_only_location_and_league'], 'alt_teams_only_tup': (g['away_ID'], g['home_ID']), 'teams_only_tup': (g['home_ID'], g['away_ID']), 'src_row': g['source_row'], 'found_on_master': 1, 'seq': len(db_updates) + 1, 'tag': 'add_game', 'home_ID': g['home_ID'], 'away_ID': g['away_ID'], 'game_desc': g['game_desc']
                            , 'home_team': None if tmp_db_home is None else tmp_db_home['display_name']
                            , 'away_team': None if tmp_db_away is None else tmp_db_away['display_name']
                            , 'location': g['location']
                            , 'game_date': g['game_date']
                            , 'desc': 'New Game.2', 'field': '[new-game]', 'from': "[empty]", 'to': "all"}
                            db_updates.append(update)
                            new_game_IDs.append(next_game_ID)
                            zc.print_dict_as_table(update)
                            if '--via-cron' not in sys.argv:
                                input("[1] New game")
                    next_game_ID += 1
                    
                else:
                    n_matches = len([1 for z in misc['db_games'] if z['tup_w_location'] == g['tup_w_location']])
                    if n_matches == 1:
                        tmp_rec =  misc['db_games'][ [z['tup_w_location'] for z in misc['db_games']].index(g['tup_w_location']) ]
                        tmp_rec_match_code = "??? 1013"
                        tmp_rec['found_on_master'] = 1
                        tmp_rec['doc_activity'] = g['game_type']
            elif g['tup'] in [z['tup'] for z in misc['db_games']]: # Already found with both teams 
                if g['both_are_placeholders']: # We need to check the location in addition to the date/teams 
                    n_matches_w_location = len([1 for z in misc['db_games'] if z['tup_w_location'] == g['tup_w_location']])
                    n_matches = len([1 for z in misc['db_games'] if z['tup'] == g['tup']])
                    
                    if n_matches >= 1 and n_matches_w_location == 1: # Single game with a single matching location
                        tmp_rec =  misc['db_games'][ [z['tup_w_location'] for z in misc['db_games']].index(g['tup_w_location']) ]
                        tmp_rec_match_code = "??? 1021"
                        tmp_rec['found_on_master'] = 1
                        tmp_rec['doc_activity'] = g['game_type']
                    elif n_matches >= 1 and n_matches_w_location == 0: # Single game between placeholders, but location is different
                        query = "INSERT INTO SDLL_Games (active, game_date, home_ID, away_ID, league, location, status, year, date_added, duration_in_hours, is_spring, is_scrimmage) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)";
                        param = [1, g['game_date'], g['home_ID'], g['away_ID'], g['league'], g['location'], 'active', year, datetime.now(), g['duration_in_hours'], IS_SPRING, g['is_scrimmage']]
                        #queries.append(query); params.append(param)
                        if g['game_date'] <= datetime.now() and datetime.now() > datetime(2025, 6, 5):
                            if 'OLDGMALT' not in ALERTS and '-quiet' not in sys.argv and '--update-assignr-games' not in sys.argv:
                                ALERTS['OLDGMALT'] = 1
                                msg = "[WARNING.b] there was at least one game from the past that was found in the master sheet, but not in the DB"
                                print(msg)
                                laxref.telegram_alert(msg)
                        else:
                            if 'NEWALTLOC' not in ALERTS and '-quiet' not in sys.argv and '--update-assignr-games' not in sys.argv and '--via-cron' in sys.argv:
                                ALERTS['NEWALTLOC'] = 1
                                msg = f"[WARNING - NEW Game added] There was a game between two placeholder teams that was already found for a given date, but the location was different, which suggests it's actually a different game in the same league among different placeholder teams\n\n{json.dumps(g, default=zc.json_handler)}"
                                print(msg)
                                if datetime.now() > datetime(2026, 5, 26):
                                    laxref.telegram_alert(msg)
                                
                            g['game_desc'] =  "%s %s (ID %s) vs %s (ID %s) @ %s" % (g['game_date'].strftime("%Y%m%d"), g['home_team'], g['home_ID'], g['away_team'], g['away_ID'], g['location'])
                            
                            misc['db_games'].append({'ID': next_game_ID
                            , 'game_date': g['game_date']
                            , 'duration_in_hours': g['duration_in_hours']
                            , 'home_ID': g['home_ID']
                            , 'away_ID': g['away_ID']
                            , 'found_on_master': 1
                            , 'is_newly_created': 1
                            , 'assignr_id': None
                            , 'umpire_override': None
                            
                            , 'tup': (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d%H"))
                            , 'tup_w_location': (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d%H"), g['location'])
                            , 'tup_w_only_location': (g['game_date'].strftime("%Y%m%d%H"), g['location'])
                            , 'tup_w_only_location_and_league': (g['game_date'].strftime("%Y%m%d%H"), g['location'], g['league'])
                            , 'tup_w_only_location_and_league_date_only': (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d"), g['location'], g['league'])
                            , 'tup_w_only_league_date_only': (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d"), g['league'])
                            , 'home_only_tup': (g['home_ID'], None, g['game_date'].strftime("%Y%m%d%H"))
                            , 'away_only_tup': (None, g['away_ID'], g['game_date'].strftime("%Y%m%d%H"))
                            , 'game_desc': g['game_desc']
                            
                            , 'league': None if g['league'] is None else g['league'].strip()
                            , 'location': None if g['location'] is None else g['location'].strip()
                            , 'status': 'active'
                            , 'year': year
                            , 'is_scrimmage': 0 if g['game_type'] == "Scrimmage" else 1
                            })

                            tmp_db_home = None
                            tmp_db_away = None
                            if g['home_ID'] is not None:
                                tmp_db_home = misc['db_teams'].get(g['home_ID'])
                            if g['away_ID'] is not None:
                                tmp_db_away = misc['db_teams'].get(g['away_ID'])
                        
                            update = {'db_game_ID': next_game_ID, 'game_type': g['game_type'], 'league': g['league'], 'proposed_query': query, 'proposed_param': param, 'tup_w_only_location_and_league': g['tup_w_only_location_and_league'], 'alt_teams_only_tup': (g['away_ID'], g['home_ID']), 'teams_only_tup': (g['home_ID'], g['away_ID']), 'src_row': g['source_row'], 'found_on_master': 1, 'seq': len(db_updates) + 1, 'tag': 'add_game', 'home_ID': g['home_ID'], 'away_ID': g['away_ID'], 'game_desc': g['game_desc']
                            , 'home_team': None if tmp_db_home is None else tmp_db_home['display_name']
                            , 'away_team': None if tmp_db_away is None else tmp_db_away['display_name']
                            , 'location': g['location']
                            , 'game_date': g['game_date']
                            , 'desc': 'New Game.2', 'field': '[new-game]', 'from': "[empty]", 'to': "all"}
                            db_updates.append(update)
                            new_game_IDs.append(next_game_ID)
                            zc.print_dict_as_table(update)
                            if '--via-cron' not in sys.argv:
                                input("[2] New game")
                    next_game_ID += 1
                    
                else:
                    n_matches = len([1 for z in misc['db_games'] if z['tup'] == g['tup']])
                    if n_matches == 1:
                        tmp_rec =  misc['db_games'][ [z['tup'] for z in misc['db_games']].index(g['tup']) ]
                        tmp_rec_match_code = "??? 1088"
                        tmp_rec['found_on_master'] = 1
            elif g['switched_tup'] in [z['tup'] for z in misc['db_games']]: # Already found with both teams 
                n_matches = len([1 for z in misc['db_games'] if z['tup'] == g['switched_tup']])
                if n_matches == 1:
                    tmp_rec =  misc['db_games'][ [z['tup'] for z in misc['db_games']].index(g['switched_tup']) ]
                    tmp_rec_match_code = "??? 1093"
                    tmp_rec['found_on_master'] = 1
                    tmp_rec['doc_activity'] = g['game_type']
                    tmp_rec['doc_activity'] = g['game_type']
                    # [May 12th, 2025] there is really no need to switch home and away IDs, for our purposes, the home/away doesn't matter
                    query = "UPDATE SDLL_Games set home_ID=%s, away_ID=%s where ID=%s;"
                    param = [g['home_ID'], g['away_ID'], tmp_rec['ID']]
                    #tmp_rec['home_ID'] = g['home_ID']
                    #tmp_rec['away_ID'] = g['away_ID']
                    
                    
                    #queries.append(query); params.append(param)
                    #update = {'db_game_ID': tmp_rec['ID'], 'src_row': g['source_row'], 'seq': len(db_updates) + 1, 'tag': 'switch_home_away', 'tup_w_only_location_and_league': g['tup_w_only_location_and_league'], 'game_desc': "%s ID %s vs ID %s" % (g['game_date'].strftime("%Y%m%d"), g['home_ID'], g['away_ID']), 'desc': 'Switch Home/Away IDs', 'field': 'home_ID', 'from': tmp_rec['home_ID'], 'to': g['home_ID']}
                    #db_updates.append(update)
                    
            elif g['game_type'] == "Rainout":
                pass                
            else: # Not found on this date; add it?
                #zc.print_dict(g)
                query = "INSERT INTO SDLL_Games (active, game_date, home_ID, away_ID, league, location, status, year, date_added, duration_in_hours, is_spring, is_scrimmage) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)";
                param = [1, g['game_date'], g['home_ID'], g['away_ID'], g['league'], g['location'], 'active', year, datetime.now(), g['duration_in_hours'], IS_SPRING, g['is_scrimmage']]
                #queries.append(query); params.append(param)
                if datetime(2026, 6, 17) < g['game_date'] <= datetime.now():
                    if 'OLDGM' not in ALERTS and '-quiet' not in sys.argv and '--update-assignr-games' not in sys.argv and '--via-cron' in sys.argv:
                        ALERTS['OLDGM'] = 1
                        msg = f"[WARNING.c] there was at least one game from the past that was found in the master sheet, but not in the DB\n\n{json.dumps(g, default=zc.json_handler)}"
                        print ("\n\nGame found on master doc, but not in DB")
                        zc.print_dict_as_table(g)
                        print(msg)
                        
                        if '--no-telegram' not in sys.argv:
                            laxref.telegram_alert(msg)
                else:
                    
                    g['game_desc'] =  "%s %s (ID %s) vs %s (ID %s) @ %s" % (g['game_date'].strftime("%Y%m%d"), g['home_team'], g['home_ID'], g['away_team'], g['away_ID'], g['location'])     
                            
                    misc['db_games'].append({'ID': next_game_ID
                    , 'game_date': g['game_date']
                    , 'duration_in_hours': g['duration_in_hours']
                    , 'home_ID': g['home_ID']
                    , 'away_ID': g['away_ID']
                    , 'found_on_master': 1
                    , 'is_newly_created': 1
                    , 'assignr_id': None
                    , 'umpire_override': None
                    
                    , 'tup': (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d%H"))
                    , 'tup_w_location': (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d%H"), g['location'])
                    , 'tup_w_only_location': (g['game_date'].strftime("%Y%m%d%H"), g['location'])
                    , 'tup_w_only_location_and_league': (g['game_date'].strftime("%Y%m%d%H"), g['location'], g['league'])
                    , 'tup_w_only_location_and_league_date_only': (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d"), g['location'], g['league'])
                    , 'tup_w_only_league_date_only': (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d"), g['league'])
                    , 'home_only_tup': (g['home_ID'], None, g['game_date'].strftime("%Y%m%d%H"))
                    , 'away_only_tup': (None, g['away_ID'], g['game_date'].strftime("%Y%m%d%H"))
                    , 'game_desc': "%s ID %s vs ID %s" % (g['game_date'].strftime("%Y%m%d"), g['home_ID'], g['away_ID'])
                    
                    , 'league': None if g['league'] is None else g['league'].strip()
                    , 'location': None if g['location'] is None else g['location'].strip()
                    , 'status': 'active'
                    , 'year': year
                    , 'is_scrimmage': 0 if g['game_type'] == "Scrimmage" else 1
                    })

                    tmp_db_home = None
                    tmp_db_away = None
                    if g['home_ID'] is not None:
                        tmp_db_home = misc['db_teams'].get(g['home_ID'])
                    if g['away_ID'] is not None:
                        tmp_db_away = misc['db_teams'].get(g['away_ID'])
                
                    update = {'db_game_ID': next_game_ID, 'game_type': g['game_type'], 'league': g['league'], 'proposed_query': query, 'proposed_param': param, 'tup_w_only_location_and_league': g['tup_w_only_location_and_league'], 'alt_teams_only_tup': (g['away_ID'], g['home_ID']), 'teams_only_tup': (g['home_ID'], g['away_ID']), 'src_row': g['source_row'], 'found_on_master': 1, 'seq': len(db_updates) + 1, 'tag': 'add_game', 'home_ID': g['home_ID'], 'away_ID': g['away_ID'], 'game_desc': g['game_desc']
                    , 'home_team': None if tmp_db_home is None else tmp_db_home['display_name']
                    , 'away_team': None if tmp_db_away is None else tmp_db_away['display_name']
                    , 'game_date': g['game_date']
                    , 'location': g['location']
                    , 'desc': 'New Game.1', 'field': '[new-game]', 'from': "[empty]", 'to': "all"}
                    db_updates.append(update)
                    new_game_IDs.append(next_game_ID)
                    next_game_ID += 1
                    zc.print_dict_as_table(update)
                    print("[3] Potential New game; will run follow-up checks to confirm")
                    #zc.print_dict_as_table(g);input("G")
                    
            # Check the non-team-ID stuff like date/time/location
            if tmp_rec is not None and tmp_rec['ID'] not in new_game_IDs and 0:
                
                if tmp_rec['ID'] not in new_game_IDs and g['location'] not in [None, ''] and laxref.hash_player_name(str(tmp_rec['location']), {'keep_numbers': 1}) != laxref.hash_player_name(str(g['location']), {'keep_numbers': 1}) and tmp_rec['game_date'].strftime("%Y%m%d%H%M") == g['game_date'].strftime("%Y%m%d%H%M"):
                    
                    
                    if g['both_are_placeholders']: # There could be multiple games on the same day for different combinations of placeholders
                        tmp_db_games = [z for z in misc['doc_games'] if g['tup_w_only_location_and_league'] == z['tup_w_only_location_and_league']]; #input("[574] Len placeholder games: %d" % len(tmp_db_games))
                        if len(tmp_db_game) == 1: # only one matched to the league and location, so we can go ahead and assume we have the correct game
                            query = "UPDATE SDLL_Games set location=%s where ID=%s;"
                            param = [g['location'], tmp_rec['ID']]
                            #queries.append(query); params.append(param)
                            
                            #g['game_desc'] =  "%s ID %s vs ID %s" % (g['game_date'].strftime("%Y%m%d"), g['home_ID'], g['away_ID'])
                            
                            update = {'db_game_ID': tmp_rec['ID'], 'game_type': g['game_type'], 'league': g['league'], 'proposed_query': query, 'proposed_param': param, 'src_row': g['source_row'], 'seq': len(db_updates) + 1, 'tag': 'location', 'game_desc': g['game_desc'], 'tup_w_only_location_and_league': g['tup_w_only_location_and_league'], 'desc': 'Update Location', 'field': 'location', 'from': tmp_rec['location'], 'to': g['location']}
                            db_updates.append(update)
                            
                            
                            tmp_rec['location'] = g['location']
                        else:
                            if 'DBLPLACEHOLDERS_GAME_UPDATE' not in ALERTS and (datetime.now() > datetime(2025, 5, 27)):
                                ALERTS['DBLPLACEHOLDERS_GAME_UPDATE'] = 1
                                tmp_msg = f"There is at least one game (league={g['league']}) where both teams are placeholders and an update was identified to the location/date/time/duration\n\nMost likely, there are multiple matches for a given day for the same placeholder combination (i.e. 2 or more schedule games for a division with specific teams not identified). Rather than flag a change, I'm alerting you to this fact so that we can re-assess if there is a better way to handle the issue."
                                print (tmp_msg)
                                if '-quiet' not in sys.argv and '--update-assignr-games' not in sys.argv:
                                    laxref.telegram_alert(tmp_msg)
                    else:
                        query = "UPDATE SDLL_Games set location=%s where ID=%s;"
                        param = [g['location'], tmp_rec['ID']]
                        #queries.append(query); params.append(param)
                        #g['game_desc'] =  "%s ID %s vs ID %s" % (g['game_date'].strftime("%Y%m%d"), g['home_ID'], g['away_ID'])
                            
                        zc.print_dict_as_table(g)
                        print("^ g (doc game)\n\n")
                        zc.print_dict_as_table(tmp_rec)
                        print("^ tmp_rec (db game)\n\n")
                        #zc.exit("FDS")
                        #update = {'db_game_ID': tmp_rec['ID'], 'game_type': g['game_type'], 'league': g['league'], 'proposed_query': query, 'proposed_param': param, 'src_row': g['source_row'], 'seq': len(db_updates) + 1, 'tag': 'location', 'game_desc': g['game_desc'], 'desc': 'Update Location', 'field': 'location', 'from': tmp_rec['location'], 'to': g['location'], 'tup_w_only_location_and_league': g['tup_w_only_location_and_league']}
                        #db_updates.append(update)
                        
                        if 2350 not in ALERTS:
                            ALERTS[2350] = 1
                            laxref.telegram_alert("[POTENTIAL LOCATION UPDATE]\n\nThere is a game where the location looks like it needs to be updated, but in the past, this was triggered because there was a game that was being moved and a game that was not being moved and both were triggering because this section is more permissive.\n\nFor now, I'm turning off the db update trigger but you should be aware of it.\n\nIn theory, if there is another game that is causing this to trigger, you should take care of that change and then this should go away.")
                        
                        tmp_rec['location'] = g['location']
                    
                if g['duration_in_hours'] not in [None, ''] and tmp_rec['duration_in_hours'] != g['duration_in_hours']:
                    
                    if g['both_are_placeholders']: # There could be multiple games on the same day for different combinations of placeholders
                        tmp_db_games = [z for z in misc['doc_games'] if g['tup_w_only_location_and_league'] == z['tup_w_only_location_and_league']]; #input("[606] Len placeholder games: %d" % len(tmp_db_games))
                        if 'DBLPLACEHOLDERS_GAME_UPDATE' not in ALERTS and (datetime.now() > datetime(2025, 5, 27)):
                            ALERTS['DBLPLACEHOLDERS_GAME_UPDATE'] = 1
                            tmp_msg = f"There is at least one game (league={g['league']}) where both teams are placeholders and an update was identified to the location/date/time/duration\n\nMost likely, there are multiple matches for a given day for the same placeholder combination (i.e. 2 or more schedule games for a division with specific teams not identified). Rather than flag a change, I'm alerting you to this fact so that we can re-assess if there is a better way to handle the issue."
                            print (tmp_msg)
                            if '-quiet' not in sys.argv and '--update-assignr-games' not in sys.argv:
                                laxref.telegram_alert(tmp_msg)
                    else:
                        query = "UPDATE SDLL_Games set duration_in_hours=%s where ID=%s;"
                        param = [g['duration_in_hours'], tmp_rec['ID']]
                        #queries.append(query); params.append(param)
                        #g['game_desc'] =  "%s ID %s vs ID %s" % (g['game_date'].strftime("%Y%m%d"), g['home_ID'], g['away_ID'])
                            
                        update = {'db_game_ID': tmp_rec['ID'], "status": "active", 'game_type': g['game_type'], 'league': g['league'], 'proposed_query': query, 'proposed_param': param, 'src_row': g['source_row'], 'seq': len(db_updates) + 1, 'tag': 'duration_in_hours', 'game_desc': g['game_desc'], 'desc': 'Update Duration', 'field': 'duration_in_hours', 'from': tmp_rec['duration_in_hours'], 'to': g['duration_in_hours'], 'tup_w_only_location_and_league': g['tup_w_only_location_and_league']}
                        db_updates.append(update)
                        
                        tmp_rec['duration_in_hours'] = g['duration_in_hours']
                    
                if g['game_date'] not in [None, ''] and tmp_rec['game_date'].strftime("%Y%m%d%H%M") != g['game_date'].strftime("%Y%m%d%H%M"):
                    
                    if g['both_are_placeholders']: # There could be multiple games on the same day for different combinations of placeholders
                        tmp_long_date = g['game_date'].strftime("%Y%m%d%H%M")
                        tmp_db_games = [z for z in misc['doc_games'] if g['tup_w_only_location_and_league'] == z['tup_w_only_location_and_league']]; #input("[626] Len placeholder games: %d (%s; %s)" % (len(tmp_db_games), g['tup_w_only_location_and_league'] ,tmp_long_date))
                        
                        if tmp_long_date in [z['game_date'].strftime("%Y%m%d%H%M") for z in tmp_db_games]: # yes there are multiple games at this location, but one of the scheduled games matches this time, so no change is needed
                            print("Potential time/location match found, no need to update")
                        else:
                            if 'DBLPLACEHOLDERS_GAME_UPDATE' not in ALERTS and (datetime.now() > datetime(2025, 5, 27)):
                                ALERTS['DBLPLACEHOLDERS_GAME_UPDATE'] = 1
                                if '--read-master-schedule' in sys.argv:
                                    tmp_msg = f"There is at least one game (league={g['league']}) where both teams are placeholders and an update was identified to the location/date/time/duration\n\nMost likely, there are multiple matches for a given day for the same placeholder combination (i.e. 2 or more schedule games for a division with specific teams not identified). Rather than flag a change, I'm alerting you to this fact so that we can re-assess if there is a better way to handle the issue."
                                    print (tmp_msg)
                                    if '-quiet' not in sys.argv and '--update-assignr-games' not in sys.argv:
                                        laxref.telegram_alert(tmp_msg)
                    elif tmp_rec['ID'] == 343 and tmp_rec['game_date'].strftime("%Y%m%d") == "20250510":
                        # There was a duplicate game record, but it's unclear why; the same team was scheduled at 9am and 11am as the home and away team in separate games against BCLL. If it was truly a doubleheader, I could probably use the double-header flag, but for now, I'm just noting it here in case this helps to figure out the edge case logic that should be used long-term.
                        pass
                    else:
                        
                        query = "UPDATE SDLL_Games set game_date=%s where ID=%s;"
                        param = [g['game_date'], tmp_rec['ID']]
                        #queries.append(query); params.append(param)  
                        #g['game_desc'] =  "%s ID %s vs ID %s" % (g['game_date'].strftime("%Y%m%d"), g['home_ID'], g['away_ID'])
                            
                        update = {'db_game_ID': tmp_rec['ID'], 'game_type': g['game_type'], 'league': g['league'], 'proposed_query': query, 'proposed_param': param, 'src_row': g['source_row'], 'seq': len(db_updates) + 1, 'tag': 'game_date', 'game_desc': g['game_desc'], 'desc': 'Update Game Date', 'field': 'game_date', 'from': tmp_rec['game_date'], 'to': g['game_date'], 'tup_w_only_location_and_league': g['tup_w_only_location_and_league']}
                        db_updates.append(update)             
                        
                        tmp_rec['game_date'] = g['game_date'] 
    
            # Check if the sheet needs to be updated with database IDs
            g['db_ID_added'] = 0; g['db_ID_updated'] = 0; g['db_ID_matched'] = 0;
            if tmp_rec is not None:
                #print ("\nDB Game")
                #zc.print_dict_as_table(tmp_rec)
                #print ("\nDoc Game")
                #zc.print_dict_as_table(g)
                if g['db_game_ID'] in [None, '']: # It hasn't been added to the sheet yet
                    g['db_ID_added'] = 1
                    ID_update_types['missing_and_added'] += 1
                    #ID_update_types_incorrect_records.append({'type': 'missing_and_added', 'source_row': g['source_row'], 'doc_game': doc_games_by_row_hashMap.get(g['source_row']), 'matched_db_game': db_games_hashMap.get(tmp_rec['ID']), 'db_game': db_games_hashMap.get(g['db_game_ID'])})
                    #ID_update_types_incorrect_rows.append("\n  Row {} ({} @ {}) was missing and has been flagged for addition".format(g['source_row'], g['game_desc'], g['location']))
                    
                elif g['db_game_ID'] != tmp_rec['ID']: # It's there, but it's different (RED FLAG!!)!)!)
                    g['db_ID_updated'] = 1
                    zc.print_dict_as_table(g)
                    ID_update_types['incorrect'] += 1
                    matched_game = db_games_hashMap.get(tmp_rec['ID'])
                    db_matched_game = db_games_hashMap.get(g['db_game_ID'])
                    ID_update_types_incorrect_rows.append("\n  Row {} ({} @ {}) matched to\nDB ID {} ({} code={}) but is listed as\nDB ID {} ({}))".format(g['source_row'], g['game_desc'], g['location'], tmp_rec['ID'], matched_game['game_desc'], tmp_rec_match_code, g['db_game_ID'], db_matched_game['game_desc']))
                    ID_update_types_incorrect_records.append({'type': 'incorrect', 'doc_game': doc_games_by_row_hashMap.get(g['source_row']), 'matched_db_game': matched_game, 'db_game': db_matched_game})
                    
                elif g['db_game_ID'] == tmp_rec['ID']: # It's there and it matches
                    g['db_ID_matched'] = 1
                    ID_update_types['correct'] += 1
                #input("has ID?")
                #print(f"Writing ID ({tmp_rec['ID']} for source row {g['source_row']}")
                
                misc['sheet_db_IDs_array'][g['source_row']-2] = [tmp_rec['ID']]
    
    # Now that we have identified a bunch of db games that were matched, we can go back through and look for team ID changes (i.e. it's a doc game that matches to a missing DB game if only the team IDs are changed.
    n_umpire_overrides = 0
    for g in misc['doc_games']:
        
        if g.get('db_game_ID') is not None:
            tmp_db_rec = db_games_hashMap.get(g['db_game_ID'])
            if tmp_db_rec is not None and g['doc_umpire_override'] != tmp_db_rec['umpire_override']:
                
                query = "UPDATE SDLL_Games set umpire_override=%s where ID=%s;"
                param = [g['doc_umpire_override'], g['db_game_ID']]
                cursor = zc.zcursor("SDLL")
                cursor.execute(query, param)
                cursor.commit()
                cursor.close()
                n_umpire_overrides += 1
        if g['a_team_was_identified'] and not g['status'] in ['cancelled']:
                
            # THere was an issue where the BCLL teams were all set to play a generic BB Majors team (which was causing multiple rows to match for a given date)
            
            tmp_rec = None # Only populated if we find a match in the DB
            tmp_rec_match_code = None
            n_matches = None
            same_league_location_time_check = g['tup_w_only_location_and_league'] in [z['tup_w_only_location_and_league'] for z in misc['db_games']]
            local_tmp_rec = None
            if same_league_location_time_check:
                local_tmp_rec =  misc['db_games'][ [z['tup_w_only_location_and_league'] for z in misc['db_games']].index(g['tup_w_only_location_and_league']) ]
            same_league_location_date_but_not_time_check = g['tup_w_only_location_and_league_date_only'] in [z['tup_w_only_location_and_league_date_only'] for z in misc['db_games']]
            local_tmp_rec_date_not_time = None
            if same_league_location_date_but_not_time_check:
                local_tmp_rec_date_not_time =  misc['db_games'][ [z['tup_w_only_location_and_league_date_only'] for z in misc['db_games']].index(g['tup_w_only_location_and_league_date_only']) ]
            
            same_league_teams_date_but_not_time_check = g['tup_w_only_league_date_only'] in [z['tup_w_only_league_date_only'] for z in misc['db_games']] and g['tup'] not in [z['tup'] for z in misc['db_games']]
            local_tmp_rec_teams_and_date_but_not_time = None
            if same_league_teams_date_but_not_time_check: # This was a game where the teams were playing on a certain date, but the time and location was different (it wasn't being flagged as a location/time change, but it should have been)
                local_tmp_rec_teams_and_date_but_not_time =  misc['db_games'][ [z['tup_w_only_league_date_only'] for z in misc['db_games']].index(g['tup_w_only_league_date_only']) ]
            
            
            
            if 0 and g['source_row'] == 991:
                zc.print_dict_as_table(g)
                
                print ("Check 1: %s" % (same_league_location_time_check))
                print ("Check 2: %s" % (same_league_location_date_but_not_time_check))
                print ("Check 3: %s" % (same_league_teams_date_but_not_time_check))
                if same_league_location_date_but_not_time_check:
                    zc.print_dict_as_table(local_tmp_rec_date_not_time)
                if same_league_teams_date_but_not_time_check:
                    zc.print_dict_as_table(local_tmp_rec_teams_and_date_but_not_time)
                
                input ("856 - PD")
                
            # There is an existing game at the same time that has had the team IDs changed; no fields or dates or times have changed, it's just the team IDs that are different; crucially, the matched DB game is no longer showing up on the master sheet (because the team IDs have switched)
            local_tmp_rec = None
            if same_league_location_time_check  and  not same_league_teams_date_but_not_time_check:
                local_tmp_rec =  misc['db_games'][ [z['tup_w_only_location'] for z in misc['db_games']].index(g['tup_w_only_location']) ]
                
            if not g['both_are_placeholders'] and same_league_location_time_check and not same_league_teams_date_but_not_time_check and ('both_are_placeholders' in local_tmp_rec and not local_tmp_rec['found_on_master'] and not local_tmp_rec['both_are_placeholders']) and None not in [g['home_ID'], g['away_ID']]: # We have a record with the home team played TBD; update?
                tmp_rec = local_tmp_rec
                tmp_rec_match_code = "Both Team IDs added"

                        
                query = "UPDATE SDLL_Games set away_ID=%s, home_ID=%s where ID=%s;"
                param = [g['away_ID'], g['home_ID'], tmp_rec['ID']]
                #queries.append(query); params.append(param)
                #tmp_rec['away_ID'] = g['away_ID']
                #tmp_rec['home_ID'] = g['home_ID']
                
                update = {'db_game_ID': tmp_rec['ID'], 'tup_w_only_location_and_league': g['tup_w_only_location_and_league'], 'tup_w_only_location_and_league': g['tup_w_only_location_and_league'], 'game_type': g['game_type'], 'league': tmp_rec['league'], 'proposed_query': query, 'proposed_param': param, 'src_row': g['source_row'], 'seq': len(db_updates) + 1, 'tag': 'both_team_IDs', 'game_desc': "{} {} vs {} @ {}".format(g['game_date'].strftime("%Y%m%d"), g['home_team'], g['away_team'], g['location']), 'desc': 'Team IDs', 'field': 'team_IDs', 'from': "%s/%s" % (tmp_rec['home_ID'], tmp_rec['away_ID']), 'to': "%s/%s" % (g['home_ID'], g['away_ID']), 'home_ID': g['home_ID'], 'away_ID': g['away_ID']}
                db_updates.append(update)
                
                
        elif g['game_type'] == "EOST" and g['home_team'] not in [None, ''] or g['away_team'] not in [None, '']:
            # Assume all playoff games are going to be played if they are on the sheet
            print("\n\n*************\n\n  TBD EOST GM [2370]\n\n******************\n\n")
            pass
        elif g['home_team'] not in [None, ''] or g['away_team'] not in [None, '']:
            zc.print_dict_as_table(g); 
            if ALERTS.get('approveAllMissingTeamUpdates'):
                print("\n\n*************\n\nBAD GM [2371]\n\n******************\n\n")
            else:
                zc.exit("BAD GM")
                #zc.print_dict(update)
                #zc.exit("UPD")
    
    if n_umpire_overrides > 0:
        msg = f"[SDLL]\n\n{n_umpire_overrides} have had their database umpire_override values updated."
        laxref.telegram_alert(msg)
        print (msg)
        
    #zc.exit("FT")            
    ignore_alerts = {}
    ignore_alerts.update({1435: datetime(2025, 10, 6)})
        
    zc.print_dict_as_table(ID_update_types)
    if '--resolve-issues' in sys.argv:
        manually_resolve_issues(ID_update_types_incorrect_records)
        
        #zc.exit("RESOLVE ISSUES")
    if '--skip-resolve-issues' not in sys.argv and ID_update_types['incorrect'] > 0 and '--update-assignr-ids' not in sys.argv:
    
        valid_ID_update_types_incorrect_rows = []
        
        for j, g in enumerate(ID_update_types_incorrect_records):
            keep_alert = 1
            
            wait_until1 = None
            tmp_game_rec = g.get('matched_db_game')
            if tmp_game_rec is not None:
                wait_until1 = ignore_alerts.get(tmp_game_rec['ID'])
                    
            if wait_until1 is not None and datetime.now() < wait_until1:
                keep_alert = 0
                #laxref.telegram_alert("[2] Alert to ignore because it's not after %s\n\n%s" % (wait_until1.strftime("%Y-%m-%d"), ID_update_types_incorrect_rows[j]))
                
            wait_until2 = None
            tmp_game_rec = g.get('db_game')
            if tmp_game_rec is not None:
                wait_until2 = ignore_alerts.get(tmp_game_rec['ID'])
                    
            if wait_until2 is not None and datetime.now() < wait_until2:
                keep_alert = 0
                #laxref.telegram_alert("[1] Alert to ignore because it's not after %s\n\n%s" % (wait_until2.strftime("%Y-%m-%d"), ID_update_types_incorrect_rows[j]))
            if keep_alert:
                valid_ID_update_types_incorrect_rows.append(ID_update_types_incorrect_rows[j])
                
        if len(valid_ID_update_types_incorrect_rows) > 0:
        
            msg = "[POTENTIALLY FATAL]\n\nThere were {} rows in the Google Sheet did mapped to a database game ID that was not the same as the one listed on the Sheet\n\n{}".format(ID_update_types['incorrect'], zc.get_original_script_command().replace(".py ", ".py  --resolve-issues"))
            if len(ID_update_types_incorrect_rows) < 3:
                msg += "\n%s" % ("\n".join(ID_update_types_incorrect_rows))
            laxref.telegram_alert(msg)
            msg = "[POTENTIALLY FATAL]\n\nThere were {} rows in the Google Sheet did mapped to a database game ID that was not the same as the one listed on the Sheet\nRows:\n{}\n\n{}".format(ID_update_types['incorrect'], "\n".join(ID_update_types_incorrect_rows), zc.get_original_script_command().replace(".py ", ".py  --resolve-issues "))
            
            zc.send_crash(msg)
            print(msg)
            zc.exit("For now we are exiting...")
    # Update the sheet with database IDs
    
    if ID_update_types['missing_and_added'] > 0 and '--update-assignr-ids' not in sys.argv:
        rangeName = 'Master!%s' % (misc['matching_db_ID_range'])
        tmp_list = [z for z in ID_update_types_incorrect_records if z['type'] == "missing_and_added"]
        #zc.print_table(ID_update_types_incorrect_records)
        #zc.exit("FFDS")
        if '--via-cron' in sys.argv:
            laxref.telegram_alert("[SDLL] There are records that need an ID added to the Google Sheet record, use --auto-update-missing-IDs flag if you'd like\n\n{}\n\n{}".format("\n".join(["src row %d" % (z['source_row']) for z in tmp_list][0:10]), json.dumps(ID_update_types, indent=1)))
        else:
            if '--auto-update-missing-IDs' in sys.argv:
                resp = "y"
            else:
                resp = input("\n Are you sure you want to update this range:   %s   This will update the Master Sheet with ID values from the SDLL_Games table. Enter y/n: " % (rangeName)).lower().strip()
            if resp == "y":
                service.spreadsheets().values().update(
                    spreadsheetId=misc['spreadsheetId'],
                    valueInputOption='RAW', range=rangeName,
                    body={'values': misc['sheet_db_IDs_array']}
                ).execute()
                print ("Updates have been executed..."); time.sleep(2)
            else:
                
                print ("OK, skipping updates for now..."); time.sleep(2 if datetime.now().strftime("%Y%m%d") != "20250923" else 0)
    
    for d in db_updates:
        d['status'] = "active"
       

    missing_games = sorted([z for z in misc['db_games'] if not z['found_on_master'] or (z['found_on_master'] and z.get('doc_activity') == "Rainout")], key=lambda x:x['game_date'])
    
    add_db_updates = [z for z in db_updates if z['tag'] == "add_game"]
    if add_db_updates != []:
        print ("\n\nNew Games (these will undergo a secondary check to make sure there is not another explanation)")
        zc.print_table(add_db_updates, {'keep_keys': ['game_desc'], 'cutoff0': 100})
    
    PRINT_MISSING_GAMES=0
    if PRINT_MISSING_GAMES:
        zc.print_table(missing_games, {'cutoff_away_ID': 9, 'cutoff_game_desc': 100, 'cutoff_home_ID': 9, 'cutoff_doc_activity': 15, 'cutoff_status': 15, 'ignore_keys': 'ID                                                                                               duration                                                                                            assignr_id                    duration_in_hours             umpire_override               is_scrimmage                  is_a_reschedule               is_newly_created              tup                           tup_w_location                tup_w_only_location           tup_w_only_location_and_le... tup_w_only_location_and_le... tup_w_only_league_date_only   orig_location                 orig_game_date                orig_home_ID                  orig_away_ID                  orig_league                   orig_duration                 home_only_tup                 away_only_tup                 teams_only_tup                alt_teams_only_tup            home_only_tup_w_location      away_only_tup_w_location      teams_only_tup_w_location tup_w_only_location_and_league tup_w_only_location_and_league_date_only    alt_teams_only_tup_w_location found_on_master               home_is_placeholder           away_is_placeholder           both_are_placeholders         '})
        zc.exit("MISSING GAMES")
    for g in missing_games:
        db_home = None if g['home_ID'] is None else misc['db_teams'].get(g['home_ID']) 
        db_away = None if g['away_ID'] is None else misc['db_teams'].get(g['away_ID']) 
        matching_new_game_rec = None
        if None not in [db_home, db_away]:
            g['home_team'] = db_home['display_name']
            g['away_team'] = db_away['display_name']
            #zc.print_dict_as_table(g); # db_game
            #zc.print_table(add_db_updates);
            #zc.exit("FDS")
            if g['teams_only_tup'] in [z['teams_only_tup'] for z in add_db_updates]:
                matching_new_game_rec = add_db_updates[ [z['teams_only_tup'] for z in add_db_updates].index(g['teams_only_tup']) ]
            elif g['tup_w_only_location_and_league'] in [z['tup_w_only_location_and_league'] for z in add_db_updates]:
                matching_new_game_rec = add_db_updates[ [z['tup_w_only_location_and_league'] for z in add_db_updates].index(g['tup_w_only_location_and_league']) ]
            elif g['alt_teams_only_tup'] in [z['teams_only_tup'] for z in add_db_updates]:
                matching_new_game_rec = add_db_updates[ [z['teams_only_tup'] for z in add_db_updates].index(g['alt_teams_only_tup']) ]
                
            
        msg = "\nIn the database, we have a game between %s (ID=%s) and %s (ID=%s) on %s @ %s (ID=%d) that is not found on the master sheet any longer." % (g.get('home_team'), g.get('home_ID'), g.get('away_team'), g.get('away_ID'), g['game_date'].strftime("%Y-%m-%d %H:%M"), g.get('location'), g['ID'])
        #print (msg)
        if matching_new_game_rec is None and '--matching-DB-game-ID' in sys.argv and '--matching-row' in sys.argv:
            if g['ID'] == int(sys.argv[sys.argv.index('--matching-DB-game-ID') + 1]):
                
                # python C:\Users\zcapo\Documents\workspace\SDLL\scratchpad.py --read-master-schedule --update-games --ignore-missing-games --no-telegram-trace --matching-row 1464 --matching-DB-game-ID 2221
                matching_new_game_rec = add_db_updates[ [z['src_row'] for z in add_db_updates].index(int(sys.argv[sys.argv.index('--matching-row') + 1])) ]
                
                zc.print_dict_as_table(matching_new_game_rec)
                print ("^ matching_new_game_rec")
                zc.print_dict_as_table(g)
                print ("^ missing Game")
                
                conf_msg = f"\n\nYou've manually specified that the database game on {g['game_date'].strftime('%b %d')} at {g['location']} between {g['away_team']} and {g['home_team']} has been modified to be {matching_new_game_rec['game_date'].strftime('%b %d')} at {matching_new_game_rec['location']} between {matching_new_game_rec['away_team']} and {matching_new_game_rec['home_team']}\n\nIs that correct? Enter y to confirm: "
                resp = input(conf_msg).lower().strip()
                if resp != "y":
                    zc.exit("Ok, exiting script")
                
                
            
            
        if matching_new_game_rec is not None:
            
            msg += "\nThere is also a new game on the master sheet between %s (ID=%s) and %s (ID=%s) on %s @ %s" % (matching_new_game_rec['home_team'], matching_new_game_rec['home_ID'], matching_new_game_rec['away_team'], matching_new_game_rec['away_ID'], matching_new_game_rec['game_date'].strftime("%Y-%m-%d %H:%M"), matching_new_game_rec['location'])
            
            
            if matching_new_game_rec['location'] == g['location'] and matching_new_game_rec['game_date'] != g['game_date']:
                print ("****************************\nLikely Reschedule!!!!!!!!!!!!!\n****************************\n")
                msg += " Since they appear to match, I would propose re-scheduling the existing game rather than deleting it."
                query1 = "UPDATE SDLL_Games set game_date=%s where ID=%s";
                
                param1 = [matching_new_game_rec['game_date'], g['ID']]
                msg += "\n\nThat would mean replacing the add game query with %s w/ %s" % (query1, param1)
                matching_new_game_rec['tag'] = "game_date"
                
                matching_new_game_rec['proposed_query'] = query1
                
                matching_new_game_rec['orig_game_date'] = g['game_date'].strftime("%Y-%m-%d %H:%M")
                matching_new_game_rec['from'] = g['game_date'].strftime("%Y-%m-%d %H:%M")
                matching_new_game_rec['to'] = matching_new_game_rec['game_date'].strftime("%Y-%m-%d %H:%M")
                matching_new_game_rec['proposed_param'] = param1
                if g['game_date'].strftime("%Y-%m-%d") != matching_new_game_rec['game_date'].strftime("%Y-%m-%d"):
                    matching_new_game_rec['desc'] = "Date Change"
                else:
                    matching_new_game_rec['desc'] = "Time Change Only"
                matching_new_game_rec['db_game_ID'] = g['ID']
                g['is_a_reschedule'] = 1
            elif matching_new_game_rec['location'] != g['location'] and matching_new_game_rec['game_date'] == g['game_date']:
                print ("****************************\nLikely Move!!!!!!!!!!!!!\n****************************\n")
                msg += " Since they appear to match, I would propose moving the location of the existing game rather than deleting it."
                query1 = "UPDATE SDLL_Games set location=%s where ID=%s";
                
                param1 = [matching_new_game_rec['location'], g['ID']]
                msg += "\n\nThat would mean replacing the add game query with %s w/ %s" % (query1, param1)
                matching_new_game_rec['tag'] = "location"
                
                matching_new_game_rec['proposed_query'] = query1
                
                matching_new_game_rec['from'] = g['location']
                matching_new_game_rec['to'] = matching_new_game_rec['location']
                matching_new_game_rec['proposed_param'] = param1
                matching_new_game_rec['desc'] = "Location Change"
                matching_new_game_rec['db_game_ID'] = g['ID']
                g['is_a_reschedule'] = 1
            elif matching_new_game_rec['location'] != g['location'] and matching_new_game_rec['game_date'] != g['game_date']:
                
                print ("****************************\nLikely Reschedule & Move!!!!!!!!!!!!!\n****************************\n")
                msg += " Since they appear to match, I would propose re-scheduling the existing game rather than deleting it."
                query = "UPDATE SDLL_Games set game_date=%s, location=%s where ID=%s";
                
                param = [matching_new_game_rec['game_date'], matching_new_game_rec['location'], g['ID']]
                msg += "\n\nThat would mean replacing the add game query with %s w/ %s" % (query, param)
                matching_new_game_rec['tag'] = "game_date"
                
                matching_new_game_rec['proposed_query'] = query
                
                matching_new_game_rec['from'] = g['game_date'].strftime("%Y-%m-%d %H:%M")
                matching_new_game_rec['to'] = matching_new_game_rec['game_date'].strftime("%Y-%m-%d %H:%M")
                matching_new_game_rec['proposed_param'] = param
                g['is_a_reschedule'] = 1
                matching_new_game_rec['desc'] = "Date & Location Chng"
                matching_new_game_rec['db_game_ID'] = g['ID']
            
            elif matching_new_game_rec['league'] == g['league'] and matching_new_game_rec['location'] == g['location'] and matching_new_game_rec['game_date'] == g['game_date'] and (matching_new_game_rec['home_ID'] != g['home_ID'] or matching_new_game_rec['away_ID'] != g['away_ID']):
                
                print ("****************************\nLikely Team Swap!!!!!!!!!!!!!\n****************************\n")
                msg += " Since they appear to match (exact date, location and league all match), I would propose changing the team IDs for the existing game rather than deleting it."
                query = "UPDATE SDLL_Games set home_ID=%s, away_ID=%s where ID=%s";
                full_query = f"UPDATE SDLL_Games set home_ID={matching_new_game_rec['home_ID']}, away_ID={matching_new_game_rec['away_ID']} where ID={g['ID']};"
                
                #print ("\n matching_new_game_rec")
                #zc.print_dict_as_table(matching_new_game_rec)
                #print ("\n g")
                #zc.print_dict_as_table(g)
                param = [matching_new_game_rec['home_ID'], matching_new_game_rec['away_ID'], g['ID']]
                msg += f"\n\nThat would mean replacing the add game query with: {full_query}"
                matching_new_game_rec['tag'] = "home_ID"
                
                matching_new_game_rec['proposed_query'] = query
                
                matching_new_game_rec['from'] = g['home_ID']
                matching_new_game_rec['to'] = matching_new_game_rec['game_date'].strftime("%Y-%m-%d %H:%M")
                matching_new_game_rec['proposed_param'] = param
                matching_new_game_rec['desc'] = "Team IDs Change"
                matching_new_game_rec['db_game_ID'] = g['ID']
                orig_update = db_updates[[z['seq'] for z in db_updates].index(matching_new_game_rec['seq']) ]
                orig_update['status'] = "inactive"
            print(msg)
            #zc.print_dict(matching_new_game_rec)
            
            
        else:
            #print ("No matching new game record (i.e. not a reschedule)")
            print ("****************************\nNo matching game -- DELETE GAME!!!!!!!!!!!!!\n****************************\n")
            msg += " The other checks that I'm using to detect a new game that is actually a reschedule did not turn up anything, which suggests that this is, in fact, a game that will need to be removed from the database. (This is uncommon; it once happened because games that should have been practices were changed to reflect that.)"
            
            print (msg)
        #input("-->")
        
    if missing_games != []:
        print ("\nMissing Games not found on Master Google Doc")
        zc.print_table(missing_games, {'cutoff*': 20, 'cutoff0': 6, 'cutoff2': 10, 'cutoff3': 10, 'cutoff5': 30, 'cutoff9': 30, 'cutoff10': 30, 'keep_keys': ["ID", "is_a_reschedule", "game_date", 'is_newly_created', "home_team", "away_team", "home_ID", "away_ID", 'league', 'location', 'assignr_id', 'doc_activity']})
        zc.print_dict_as_table(missing_games[0])
        summary_of_missing_games = {}
        for g in missing_games:
            tmp_s = "%s - %s" % (g['league'], g['game_date'].strftime("%a %b %d"))
            summary_of_missing_games[tmp_s] = summary_of_missing_games.get(tmp_s, 0) + 1
        
        # If it's a known issue, we can postpone the alert (i.e. we have a reschedule that has been removed from the schedule but has not yet had the date reset)
        valid_alert_missing_games = []
        for g in missing_games:
            keep_alert = 1
            wait_until = ignore_alerts.get(g['ID'])
            if wait_until is not None and datetime.now() < wait_until:
                keep_alert = 0
            if keep_alert:
                valid_alert_missing_games.append(g)
        
        send_it = 0
        if len(valid_alert_missing_games) > 0 and '--update-assignr-games' not in sys.argv and datetime.now() > datetime(2026, 8, 10) and '--via-cron' in sys.argv:
            send_it = 1
        
        #if send_it and datetime.now() < datetime(2026, 6, 10) and len(missing_games) == 6 and len(summary_of_missing_games) == 5:
        #    send_it = 0
            
        if send_it:
            laxref.telegram_alert("[SDLL WARNING 1283]\n\nWe have %d games in the SDLL database that are not showing up on the Master Sheet. Either figure out what real game they should match to or delete them from the database.\n\n%s\n\nIf these games do actually match to existing Master sheet games, you can use the --matching-row / --matching-DB-game-ID flags to identify them manually" % (len(missing_games), zc.print_dict_as_table(summary_of_missing_games)))
    
    rescheduled_games_with_no_assignr_id = [z for z in missing_games if not z['is_newly_created'] and z['is_a_reschedule'] and z['assignr_id'] in ['NONE', None, '']]
    missing_games_with_no_assignr_id = [z for z in missing_games if not z['is_newly_created'] and not z['is_a_reschedule'] and z['assignr_id'] in ['NONE', None, '']]
    non_rescheduled_missing_games = [z for z in missing_games if not z['is_a_reschedule']]
    
    # [2025-09-02] Since we are now handling all games, regardless of whether they require a young umpire, this check is irrelevant
    if 0 and len(missing_games_with_no_assignr_id) > 0:
        
            
        if len(rescheduled_games_with_no_assignr_id) > 0:
            msg = "\nThere are %d games that are stored in the local DB, but are not found on the master sheet (note: there were also %d games that appear to be reschedules) AND have not had an assignr_id set (meaning there is no umpire impact). Can I delete them: (y/n) " % (len(missing_games_with_no_assignr_id), len(rescheduled_games_with_no_assignr_id))
        else:
            msg ="\nThere are %d games that are stored in the local DB, but are not found on the master sheet AND have not had an assignr_id set (meaning there is no umpire impact). Can I delete them: (y/n) " % len(missing_games_with_no_assignr_id)
            
        if '--ignore-missing-games' not in sys.argv:
            if '--via-cron' in sys.argv and '--update-assignr-games' not in sys.argv:
                laxref.telegram_alert(msg)
            else:
                resp = input(msg)
                if resp == "y":
                    cursor = zc.zcursor("SDLL")
                    cursor.executemany("UPDATE SDLL_Games set active=0 where ID=%s;", [[z['ID']] for z in missing_games_with_no_assignr_id])
                    cursor.commit()
                    cursor.close()

    if len(non_rescheduled_missing_games) > 0 and '--ignore-missing-games' not in sys.argv and '--update-assignr-games' not in sys.argv:
        zc.exit("NOT FOUND (to ignore this use --ignore-missing-games flag")
        
    if '--change-desc' in sys.argv:
        db_updates = [z for z in db_updates if z['desc'] == sys.argv[sys.argv.index('--change-desc') + 1]]
    if '-league' in sys.argv:
        db_updates = [z for z in db_updates if z['league'] == sys.argv[sys.argv.index('-league') + 1]]
        
    db_updates_by_league_and_game_type_and_update_type = defaultdict(list)
    for update in db_updates:
        db_updates_by_league_and_game_type_and_update_type[update['league'] + " - " + update['game_type'] + ' - ' + update['tag']].append(update)
    
    db_updates_by_league_and_game_type_and_update_type = dict(sorted(db_updates_by_league_and_game_type_and_update_type.items()))
    db_updates_by_league_and_game_type_and_update_type_msg = ""
    for k in db_updates_by_league_and_game_type_and_update_type:
        db_updates_by_league_and_game_type_and_update_type_msg += "\n{}: {}".format(k, "{:,} update(s)".format(len(db_updates_by_league_and_game_type_and_update_type[k])))
        
    if '--update-games' in sys.argv and '--update-assignr-games' not in sys.argv:
        

        
        queries = [z['proposed_query'] for z in db_updates if z['status'] == "active"]
        params = [z['proposed_param'] for z in db_updates if z['status'] == "active"]
        if len(params) > 0:
            
            game_db_updates = defaultdict(list)
            for z in db_updates:
                z['processed'] = 0
                if z['status'] == "active":
                    game_db_updates[z['db_game_ID']].append(z)
            
                
            keep_looping = None

            while keep_looping is None or keep_looping:
                keep_looping = 0
                print ("\n\n Game Updates")
                zc.print_table([z for z in db_updates if not z['processed'] and z['status'] == "active"], {'ignore_keys': ['alt_teams_only_tup', 'home_ID', 'away_ID', 'tup_w_only_location_and_league', 'tag', 'status', 'field', 'teams_only_tup', 'home_team', 'away_team', 'proposed_query', 'proposed_param', 'location', 'found_on_master'], 'cutoff0': 10, 'cutoff1': 10, 'cutoff2': 15, 'cutoff3': 6, 'cutoff4': 6, 'cutoff5': 105, 'cutoff6': 20, 'cutoff_desc': 30, 'cutoff_processed': 10, 'cutoff_this_loop': 10})
                print ("\n\nNote: use this to limit yourself to specific types of updates (i.e. keep simple time changes only")
                cmd = "python C:\\Users\\zcapo\\Documents\\workspace\\SDLL\\scratchpad.py  --read-master-schedule  --update-games --change-desc \"[desc]\""
                if '--ignore-missing-games' in sys.argv:
                    cmd = "python C:\\Users\\zcapo\\Documents\\workspace\\SDLL\\scratchpad.py --ignore-missing-games --read-master-schedule  --update-games --change-desc \"[desc]\""
                print (cmd)
                
                db_updates_by_leagues = defaultdict(list)
                db_updates_by_league_and_game_types = defaultdict(list)
                placeholders_by_league_and_game_types = defaultdict(list)
                for update in db_updates:
                    if not update['processed']:
                        db_updates_by_leagues[update['league']].append(update)
                        db_updates_by_league_and_game_types[update['league'] + " - " + update['game_type']].append(update)
                
                which_desc = [{'desc': y} for y in list(set([z['desc'] for z in db_updates if not z['processed']]))]
                which_league = [{'league': y} for y in list(set([z['league'] for z in db_updates if not z['processed']]))]
                
                n_placeholder_games = 0
                for update in misc['doc_games']:
                    if not update['a_team_was_identified']:
                        placeholders_by_league_and_game_types[update['league']].append(update)
                        if update['league'] not in ['Tee Ball', '']:
                            n_placeholder_games += 1
                        
                print ("\nTotal updates")
                db_updates_by_leagues = dict(sorted(db_updates_by_leagues.items()))
                for k in db_updates_by_leagues:
                    print ("{:<30}{:<30}".format(k, "{:,} update(s)".format(len(db_updates_by_leagues[k]))))
               
                print ("\nTotal updates by game type")
                db_updates_by_league_and_game_types = dict(sorted(db_updates_by_league_and_game_types.items()))
                for k in db_updates_by_league_and_game_types:
                    print ("{:<30}{:<30}".format(k, "{:,} update(s)".format(len(db_updates_by_league_and_game_types[k]))))
            
                print ("\nTotal updates by game type and update type")
                print (db_updates_by_league_and_game_type_and_update_type_msg)
            
                print ("\nPlaceholder games not being added to the DB (because a_team_was_identified=0)")
                placeholders_by_league_and_game_types = dict(sorted(placeholders_by_league_and_game_types.items()))
                for k in placeholders_by_league_and_game_types:
                    print ("{:<30}{:<30}".format(k, "{:,} update(s)".format(len(placeholders_by_league_and_game_types[k]))))
                n_valid_misc_doc_games = len([1 for g in misc['doc_games'] if g['a_team_was_identified'] and not g['status'] in ['cancelled']])
                
                selected_desc = None
                selected_league = None
                
                if '--just-notify' in sys.argv:
                    resp = "n"
                else:
                    resp = "review"
                    while resp == "review":
                        resp = input("\nGo ahead with %d updates (relative to %d valid records and %d placeholders on Master) (y/n/review/select)? " % (len(params), n_valid_misc_doc_games, n_placeholder_games))
                        if resp == "review":
                            for query, param in zip(queries, params):
                                print ("Query %s /w %s" % (query, param))
                                
                        elif resp == "select":
                            go_on = 0
                            zc.print_table(which_desc)
                            zc.print_table(which_league)
                            while not go_on:
                                print("\n\nMake your choices\n\n")
                                msg_ = "\nWhich type of change do you want to execute?:\n\n%s\n - all\n\n--> " % ("\n".join([f" - {z['desc']}" for z in which_desc]))
                                selected_desc = input(msg_)
                                msg_ = "\nWhich league do you want to execute?:\n\n%s\n - all\n\n--> " % ("\n".join([f" - {z['league']}" for z in which_league]))
                                selected_league = input(msg_)
                                
                                valid_choices1 = [z['desc'] for z in which_desc] + ['all']
                                valid_choices2 = [z['league'] for z in which_league] + ['all']
                                if selected_desc in valid_choices1 and selected_league in valid_choices2:
                                    go_on = 1
                                keep_looping = 1
                if resp != "y" and resp != "select":
                    zc.exit("EXITING...")
                    
                for update in db_updates:
                    update['this_loop'] = 1
                    if selected_league not in [None, 'all']:
                        if update['league'] != selected_league:
                            update['this_loop'] = 0
                    if selected_desc not in [None, 'all']:
                        if update['desc'] != selected_desc:
                            update['this_loop'] = 0
                            
                selected_queries = [z['proposed_query'] for z in db_updates if not z['processed'] and z['this_loop'] and z['status'] == "active"]
                selected_params = [z['proposed_param'] for z in db_updates if not z['processed'] and z['this_loop'] and z['status'] == "active"]
                for query, param in zip(selected_queries, selected_params):
                    print ("Query %s /w %s" % (query, param))
                    
                input("[Queries; press enter to execute them]")
                cursor = zc.zcursor("SDLL")
                for query, param in zip(selected_queries, selected_params):
                    if "INSERT INTO SDLL_Games" in query and '--initial-game-load' not in sys.argv:
                        input ("\n\n[Press enter to go ahead with new game addition; you can use --initial-game-load if we should auto-approve games]\n\nQuery %s /w %s" % (query, param))
                    else:
                        print ("Query %s /w %s" % (query, param))
                    cursor.execute(query, param)
                
                # Insert updates into the SDLL_Game_Updates table
                for ij, game_ID in enumerate(game_db_updates):
                    #print ("Update %d / %d (game_ID=%d)" % (ij+1, len(game_db_updates), game_ID))
                
                    db_game_rec = db_games_hashMap.get(game_ID)
                    old_location, new_location, old_game_date, new_game_date, old_home_ID, new_home_ID, old_away_ID, new_away_ID, old_duration, new_duration = None, None, None, None, None, None, None, None, None, None
                    hash
                    
                    for update in game_db_updates[game_ID]:
                        if not update['this_loop'] or update['processed']:
                            continue
                        else:    
                            zc.print_dict_as_table(update)
                            update['processed'] = 1
                            if update['desc'] == "Update Location" and db_game_rec['orig_location'] != update['to']:
                         
                                old_location = db_game_rec['orig_location']
                                new_location = update['to']
                            elif update['desc'] in ["Time & Location Change", "Date & Location Chng"] and db_game_rec['orig_location'] != update['location']:
                         
                                old_location = db_game_rec['orig_location']
                                new_location = update['location']
                                old_game_date = db_game_rec['orig_game_date']
                                new_game_date = update['game_date']
                                #zc.print_dict_as_table(update)
                                #zc.exit("UPD")
                            elif update['desc'] in ["Time Change Only", "Date/Time Change", "Date Change", "Update Game Date"] and db_game_rec['orig_game_date'] != update['to']:
                                
                                old_game_date = db_game_rec['orig_game_date']
                                new_game_date = update['to']
                            elif update['desc'] in ["Location Change Only"] and db_game_rec['orig_location'] != update['to']:
                                
                                old_location = db_game_rec['orig_location']
                                new_location = update['to']
                            elif update['desc'] == "Update Home Team" and db_game_rec['orig_home_ID'] != update['to']:
                                
                                old_home_ID = db_game_rec['orig_home_ID']
                                new_home_ID = update['to']
                            elif update['desc'] in ["Team IDs", "Team IDs Change", "Update Single Placeholder"] and (db_game_rec['orig_away_ID'] != update['away_ID'] or db_game_rec['orig_home_ID'] != update['home_ID']):
                                
                                if db_game_rec['orig_away_ID'] != update['away_ID']:
                                    old_away_ID = db_game_rec['orig_away_ID']
                                    new_away_ID = update['away_ID']
                                if db_game_rec['orig_home_ID'] != update['home_ID']:
                                    old_home_ID = db_game_rec['orig_home_ID']
                                    new_home_ID = update['home_ID']
                            elif update['desc'] == "Update Away Team" and db_game_rec['orig_away_ID'] != update['to']:
                                
                                old_away_ID = db_game_rec['orig_away_ID']
                                new_away_ID = update['to']
                            elif update['desc'] == "Update Duration" and db_game_rec['orig_duration'] != update['to']:
                                
                                old_duration = db_game_rec['orig_duration']
                                new_duration = update['to']
                            elif update['tag'] == "add_game":
                                pass # Handled below
                                
                            else:
                                msg = "[FATAL SDLL BUG]\n\nThere is an unhandled update.desc value: %s" % update['desc']
                                laxref.telegram_alert(msg)
                                zc.exit(msg)
                                
                    insert_query = "INSERT INTO SDLL_Game_Updates (active, game_ID, datestamp, old_location, new_location, old_game_date, new_game_date, old_home_ID, new_home_ID, old_away_ID, new_away_ID, old_duration_in_hours, new_duration_in_hours, added_via) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);"
                    insert_param = [1, game_ID, datetime.now(), old_location, new_location, old_game_date, new_game_date, old_home_ID, new_home_ID, old_away_ID, new_away_ID, old_duration, new_duration, "autoDBUpdates"]
                    print ("Query %s w/ %s" % (insert_query, insert_param))
                    cursor.execute(insert_query, insert_param)
                
                # Insert new game records into the SDLL_Game_Updates table
                for ij, game_ID in enumerate(game_db_updates):
            
                    #print ("New Game %d / %d" % (ij+1, len(game_db_updates)))
                    db_game_rec = db_games_hashMap.get(game_ID)
                    #old_location, new_location, old_game_date, new_game_date, old_home_ID, new_home_ID, old_away_ID, new_away_ID = None, None, None, None, None, None, None, None
                    #hash
                    
                    for update in game_db_updates[game_ID]:
                        if not update['this_loop'] or update['processed']:
                            continue
                        else:    
                            zc.print_dict_as_table(update)
                            #zc.print_dict_as_table(update)
                            if update['tag'] == "add_game":
                         
                                insert_query = "INSERT INTO SDLL_Game_Updates (active, game_ID, datestamp, added_via) VALUES (%s, %s, %s, %s);"
                                insert_param = [1, game_ID, datetime.now(), "newGameInserts"]
                                print(" Query %s w/ %s" % (insert_query, insert_param))
                                cursor.execute(insert_query, insert_param)
                                update['processed'] = 1
                                
                n_game_db_updates_cumulative = sum([len(v) for k, v in game_db_updates.items()])    
                if n_game_db_updates_cumulative != len(params):
                    
                    if '--via-cron' in sys.argv:
                        
                        laxref.telegram_alert("Error 1423 - not enough change queries %d vs %d" % (n_game_db_updates_cumulative, len(params)))
                    else:
                        print ("\nQueries")
                        print (queries)
                        print ("\nDB Updates")
                        zc.print_table(game_db_updates)
                        input("\n\nError 1423 - not enough change queries %d vs %d (see list above)" % (n_game_db_updates_cumulative, len(params)))
                cursor.commit()
                cursor.close()
    else:
        if (len(db_updates) > 0 or len(params) > 0) and '-quiet' not in sys.argv:

            msg = (f"There are {len(db_updates)} game updates required to get the DB to match the google doc\n\n{db_updates_by_league_and_game_type_and_update_type_msg}")
            if '--update-assignr-games' not in sys.argv:
                laxref.telegram_alert("[SDLL WARNING]\n\n{}".format(msg))
            print (msg)
    
    print ("Done with fn.read_master_schedule...")
    return misc

def compile_schedule_changes():
    print('--compile-schedule-changes')
    # python scratchpad.py --compile-schedule-changes -since 20250912
    
    year = datetime.now().year
    misc = {}
    
    cursor = zc.zcursor("SDLL")
    misc['db_games'] = cursor.dqr("""Select a.ID game_ID, a.game_date, a.location, a.league, a.is_scrimmage
, c.team_ID home_ID,  c.display_name home_team
, b.team_ID away_ID,  b.display_name away_team
from SDLL_Games a LEFT JOIN SDLL_Team_Seasons b ON b.team_ID=a.away_ID  LEFT JOIN SDLL_Team_Seasons c ON c.team_ID=a.home_ID where  a.year=%s and a.is_spring=%s;""", [year, IS_SPRING])
    misc['db_teams'] = {z['team_ID']: z for z in cursor.dqr("SELECT team_ID, display_name, league, IFNULL(is_placeholder, 0) is_placeholder FROM SDLL_Team_Seasons where active and year=%s and is_spring=%s;", [year, IS_SPRING])}

    query = "SELECT ID, active, game_ID, datestamp, old_location, new_location, old_game_date, new_game_date, added_via, old_home_ID, new_home_ID, old_away_ID, new_away_ID from SDLL_Game_Updates where active order by datestamp desc;"
    param = []
    misc['game_change_records'] = cursor.dqr(query, param)
    
    
    misc['alternate_names'] = cursor.dqr("SELECT a.ID, a.team_ID, a.alternate_name, b.display_name actual_name from SDLL_Alternate_Team_Names a, SDLL_Team_Seasons b where b.is_spring=%s and b.active and a.team_ID=b.team_ID and a.year=b.year and a.active and a.year=%s;", [IS_SPRING, year])

    cursor.close()
    
    since_cutoff = None
    if '-since' in sys.argv:
        since_cutoff = datetime.strptime(sys.argv[sys.argv.index('-since') + 1], "%Y-%m-%d" if "-" in sys.argv[sys.argv.index('-since') + 1] else "%Y%m%d")
    game_changes_defaultdict = defaultdict(list)
    for r in misc['game_change_records']:
        r['in_last_30_days'] = 1 if (datetime.now() - r['datestamp']).total_seconds() < 3600 * 24 * 30 else 0
        r['since_cutoff'] = None
        if since_cutoff is not None:
            r['since_cutoff'] = 1 if (r['datestamp'] > since_cutoff) else 0
            if r['since_cutoff']:
                game_changes_defaultdict[r['game_ID']].append(r)
        else:
            if r['in_last_30_days']:
                game_changes_defaultdict[r['game_ID']].append(r)
        
        
        
        
    
    misc, service = read_from_google_sheet("all_games_master_doc", misc, {})
    misc, service = read_from_google_sheet("teamKey", misc, {})
    misc = convert_master_sheet_data_to_games(misc, service, {'version': 1})
    
    zc.print_table(misc['db_games'][0:10])
    for g in misc['db_games']:
        g['changes'] = game_changes_defaultdict.get(g['game_ID'])
        
        
    w_changes = [z for z in misc['db_games'] if z['changes'] is not None]
    for g in w_changes:
        g['change_strings'] = []
    
        tmp_list = [z for z in g['changes'] if z['old_location'] is not None]
        g['old_location'] = None if tmp_list == [] else tmp_list[-1]['old_location']
        tmp_list = [z for z in g['changes'] if z['new_location'] is not None]
        g['new_location'] = None if tmp_list == [] else tmp_list[0]['new_location']
        g['location_changed'] = 0 
        if g['new_location'] is not None and g['old_location'] != g['new_location']:
            g['location_changed'] = 1 
            if g['old_location'] is not None:
                g['location_change_desc'] = f"was moved from {g['old_location']} to {g['new_location']}"
            else:
                g['location_change_desc'] = f"has been scheduled for {g['new_location']}"
                
            g['change_strings'].append( g['location_change_desc'] )
            
        tmp_list = [z for z in g['changes'] if z['old_game_date'] is not None]
        g['old_game_date'] = None if tmp_list == [] else tmp_list[-1]['old_game_date']
        tmp_list = [z for z in g['changes'] if z['new_game_date'] is not None]
        g['new_game_date'] = None if tmp_list == [] else tmp_list[0]['new_game_date']
        g['game_date_changed'] = 0; g['game_time_changed'] = 0 
        if g['new_game_date'] is not None and (g['old_game_date'] is None or laxref.simple_strftime(g['old_game_date']) != laxref.simple_strftime(g['new_game_date'])):
            g['game_date_changed'] = 1 
            if g['old_game_date'] is None:
                g['rescheduled_movement'] = "%s%s @ %s" % (g['new_game_date'].strftime("%a %b %d").replace(" 0", " "), zc.get_number_suffix(g['new_game_date'].day), g['new_game_date'].strftime("%I:%M %p"))
            else:
                g['rescheduled_movement'] = "%s%s @ %s to %s%s @ %s" % (g['old_game_date'].strftime("%a %b %d").replace(" 0", " "), zc.get_number_suffix(g['old_game_date'].day), g['old_game_date'].strftime("%I:%M %p"), g['new_game_date'].strftime("%a %b %d").replace(" 0", " "), zc.get_number_suffix(g['new_game_date'].day), g['new_game_date'].strftime("%I:%M %p"))
        if g['new_game_date'] is not None and (g['old_game_date'] is None or g['old_game_date'].strftime("%Y%m%d%H%M") != g['new_game_date'].strftime("%Y%m%d%H%M")):
            g['game_time_changed'] = 1 
            if g['old_game_date'] is None:
                g['game_time_movement'] = g['new_game_date'].strftime("%I:%M %p")
            else:
                g['game_time_movement'] = "%s to %s" % (g['old_game_date'].strftime("%I:%M %p"), g['new_game_date'].strftime("%I:%M %p"))
            
        if g['game_time_changed'] and g['game_time_changed'] and not g['game_date_changed']:
            g['game_date_change_desc'] = f"time has been changed from {g['game_time_movement']}"
            g['change_strings'].append( g['game_date_change_desc'] )
        elif g['game_date_changed']:
            if g['old_game_date'] is None:
                g['game_date_change_desc'] = f"scheduled for {g['rescheduled_movement']}"
            else:
                g['game_date_change_desc'] = f"rescheduled from {g['rescheduled_movement']}"
            g['change_strings'].append( g['game_date_change_desc'] )
        g['full_change_str'] = " and ".join(g['change_strings'])    
        
    w_changes = [z for z in w_changes if z['game_time_changed'] or z['location_changed'] or z['game_date_changed']]
    for g in w_changes:
        if not g['location_changed'] and g['game_time_changed'] and not g['game_date_changed']:
            g['full_change_str'] = "For the %s game @ %s between %s and %s, the %s" % (g['game_date'].strftime("%a %b %d"), g['location'], g['home_team'], g['away_team'], g['full_change_str'])
        elif g['location_changed'] and g['old_location'] is not None and not g['game_date_changed'] and not g['game_time_changed']:
            g['full_change_str'] = "The %s game @ %s has been %s" % (g['game_date'].strftime("%a %b %d"), g['old_location'], g['full_change_str'])
        else:
            zc.print_dict_as_table(g)
            
            zc.exit("ER")
            
    zc.print_table(w_changes, {'keep_keys': ["game_ID", "location", "game_date", "league", "game_date_changed", "game_time_changed", "location_changed", "home_team", "away_team"]})        
        
    sb_rookie = [{
    'league': z['league']
    , 'game_date': z['game_date' if z['new_game_date'] is None else 'new_game_date']
    , 'location': z['location' if z['new_location'] is None else 'new_location']
    , 'full_change_str': z['full_change_str']
    } for z in w_changes if z['league'] == "SB Rookie"]
    if len(sb_rookie) > 0:
        print ("\n\n[SB Rookie]\n\n");zc.print_dict(sb_rookie)
        
    other_softball = [{
    'league': z['league']
    , 'game_date': z['game_date' if z['new_game_date'] is None else 'new_game_date']
    , 'location': z['location' if z['new_location'] is None else 'new_location']
    , 'full_change_str': z['full_change_str']
    } for z in w_changes if "SB" in z['league'] and z['league'] != "SB Rookie"]
    if len(other_softball) > 0:
        print ("\n\n[SB Other]\n\n");zc.print_dict(other_softball)
        
    baseball = [{
    'league': z['league']
    , 'game_date': z['game_date' if z['new_game_date'] is None else 'new_game_date']
    , 'location': z['location' if z['new_location'] is None else 'new_location']
    , 'full_change_str': z['full_change_str']
    } for z in w_changes if "BB" in z['league']]
    if len(baseball) > 0:
        print ("\n\n[Baseball]\n\n");zc.print_dict(baseball)
        
    print ("Done with fn.compile_schedule_changes...")
    return misc
    
def retrieve_umpire_feedback_from_standings_google_sheets():
    print('--retrieve-umpire-feedback-from-standings-google-sheets')
    # python scratchpad.py --retrieve-umpire-feedback-from-standings-google-sheets
    divisions = []
    divisions.append({'league': 'BB Intermediate', 'alt_name': 'Intermediate', 'sheet_id': "1rnUBq_dqxBFWEj9s5KRibaiL0RyWd6RXmuLoekcE2Wg"})
    divisions.append({'league': 'BB AAA', 'alt_name': 'Grapefruit', 'alt_name_2': 'BB Grapefruit', 'sheet_id': "1Fd1qbKP68CcGpHz2ZVRP2jl2koW_tSpmMVm5RLwdyu4"})
    divisions.append({'league': 'BB AA', 'alt_name': 'Cactus', 'alt_name_2': 'BB Cactus', 'sheet_id': "1n7NK2v5JTPJqL9LVFgln4dPbnuIv6ik9rS7d0z7nPCE"})
    divisions.append({'league': 'BB A', 'alt_name': 'UMP', 'alt_name_2': 'BB UMP', 'sheet_id': "1hzdURuNi-8DEKAnDNljpLmOSV9N7WdetoBejRNDnqLQ"})
    divisions.append({'league': 'BB Rookie', 'alt_name': 'LMP', 'alt_name_2': 'BB LMP', 'sheet_id': "1hLXtUsQSJ3M7Tq-G21UaPY3lX29u9vfpFdA2rJmp4EA"})
    
    divisions_hashMap = {z['league']: z for z in divisions}
    misc = {}
    
    misc, service = read_from_google_sheet("umpireFeedback", misc, {'divisions': divisions})
    misc, service = read_from_google_sheet("all_games_master_doc", misc, {})
    misc, service = read_from_google_sheet("teamKey", misc, {})
    misc = convert_master_sheet_data_to_games(misc, service, {'version': 1})
    
    cursor = zc.zcursor("SDLL")
    db_teams_display_name_hashMap = {z['display_name']: z for z in cursor.dqr("SELECT team_ID, display_name, league, IFNULL(is_placeholder, 0) is_placeholder FROM SDLL_Team_Seasons where active and year=%s and is_spring=%s;", [datetime.now().year, IS_SPRING])}
    cursor.close()
    
    print ("\n Last name Lookup")
    for k, v in misc['coaches_last_name_lookup'].items():
        print ("\nTup: %s" % str(k))
        print(v)
    #print(json.dumps(misc['coaches_last_name_lookup'], indent=1))

    for division in divisions:
        if 'sheets' in division:
            print ("Division: %s" % division['alt_name'])
            zc.print_dict_as_table(division)
            
            for sht in division['sheets']:
                zc.print_dict_as_table(sht)
                tups = [(division['league'], sht['title'])]
                if division.get("alt_name_2") is not None:
                    tups.append((division['alt_name_2'], sht['title']))
                for tup in tups:
                    print ("tup: %s" % str(tup))
                    team_rec = misc['coaches_last_name_lookup'].get(tup)
                    if team_rec is None:
                        print ("  Error")
                        if 2192 not in ALERTS:
                            ALERTS[2192] = 1
                            msg = "[SDLL ERROR] Could not identify a coach (from teamKey) record associated with %s" % (str(tup))
                            print(msg)
                            laxref.telegram_alert(msg)
                    else:
                        print ("Associated Team Name")
                        print(team_rec)
                        db_team = db_teams_display_name_hashMap.get(team_rec)
                        if db_team is not None:
                            zc.print_dict(db_team)
                        else:
                            print ("  DB Match Failed")
                            if 2200 not in ALERTS:
                                ALERTS[2200] = 1
                                msg = "[SDLL ERROR] Could not identify a DB team record associated with %s" % (team_rec)
                                print(msg)
                                laxref.telegram_alert(msg)
                        break
        
    
UMPIRE_IDS_BY_NAME = {}    
def show_assignr_counts_by_umpires():
    print('--show-assignr-counts-by-umpires')
    # python scratchpad.py --show-assignr-counts-by-umpires
    # python scratchpad.py --show-assignr-counts-by-umpires --add-emails
    # ^ Will include the email addresses associated with each umpire and print out a list at the end of the script
    
    
    year = datetime.now().year
    if '-year' in sys.argv:
        year = int(sys.argv[sys.argv.index('-year') + 1])
    misc = {}
    
    cursor = zc.zcursor("SDLL")
    misc['db_games'] = cursor.dqr("""Select a.ID game_ID, a.game_date, a.location, a.league
, c.team_ID home_ID,  c.display_name home_team
, b.team_ID away_ID,  b.display_name away_team
from SDLL_Games a LEFT JOIN SDLL_Team_Seasons b ON b.team_ID=a.away_ID  LEFT JOIN SDLL_Team_Seasons c ON c.team_ID=a.home_ID where  a.year=%s and a.is_spring=%s;""", [year, IS_SPRING])
    misc['db_teams'] = {z['team_ID']: z for z in cursor.dqr("SELECT team_ID, display_name, league, IFNULL(is_placeholder, 0) is_placeholder FROM SDLL_Team_Seasons where active and year=%s and is_spring=%s;", [year, IS_SPRING])}

    
    cursor.close()
    
    
        
    
    misc, service = read_from_google_sheet("all_games_master_doc", misc, {})
    misc = convert_master_sheet_data_to_games(misc, service, {'version': 1})
    games_by_umpire = defaultdict(list)
    assignr_games = read_assignr_games(all_games=1)
    for g in assignr_games:
        games_by_umpire[g['umpire_str']].append(g)
        #zc.print_dict(g)
    umpires = [{'umpire': k, 'id': UMPIRE_IDS_BY_NAME.get(k)} for k in games_by_umpire]

    all_emails = []
    if '--add-emails' in sys.argv:
        for umpire in umpires:
            zc.print_dict_as_table(umpire)
           
            UMPIRE_ID=umpire['id']
            url = f"https://api.assignr.com/api/v2/users/{UMPIRE_ID}"
            print (url)
            g['no_umpire_assigned'] = 0
            headers = {"accept": "application/json"}
            #response = requests.get(url, headers=headers)
            response = assignr_request(url)
            tmp_emails = (response.get('email_addresses'))
            if tmp_emails is not None:
                all_emails += tmp_emails
                tmp_emails = ", ".join(tmp_emails)
            umpire['umpire_emails'] = tmp_emails
                                        
    for u in umpires:
        tmp_games = games_by_umpire.get(u['umpire'])
        u['n_games'] = len(tmp_games)
        u['first_game'] = min([z['game_date'] for z in tmp_games])
        u['last_game'] = max([z['game_date'] for z in tmp_games])
        
        # Group their games by day of the week
        days_of_the_week = {}
        for g in tmp_games:
            days_of_the_week[g['game_date'].strftime("%a")] = days_of_the_week.get(g['game_date'].strftime("%a"), 0) + 1
        days_of_the_week = dict(sorted(days_of_the_week.items(), key=lambda x:x[1], reverse=True))
        u['favorite_day'] = "%s (%d games)" % (list(days_of_the_week.keys())[0], list(days_of_the_week.values())[0])
        if len(days_of_the_week.keys()) == 1:
            u['least_favorite_day'] = ""
        else:
            u['least_favorite_day'] = "%s (%d games)" % (list(days_of_the_week.keys())[-1], list(days_of_the_week.values())[-1])
        
        # Group their games by league
        leagues = {}
        for g in tmp_games:
            leagues[g['league']] = leagues.get(g['league'], 0) + 1
        leagues = dict(sorted(leagues.items(), reverse=True))
        u['favorite_league'] = "%s (%d games)" % (list(leagues.keys())[0], list(leagues.values())[0])
        
        
    umpires = sorted(umpires, key=lambda x:x['n_games'], reverse=True)
    zc.print_table(umpires, {'cutoff*': 20, 'ignore_keys': ['id', 'account_id']})
    
    if '--add-emails' in sys.argv:
        print ("\nThese are the emails for all umpires who did at least one game in the prior season:\n")
        print (", ".join(sorted(all_emails)))
    print ("Done with fn.show_assignr_counts_by_umpires...")
    return misc

   
    
    
    
def get_assignr_token():
    API_KEY=json.loads(open(os.path.join(sdll_fldr, "client_secrets.json"), 'r').read())['local']['assignr_client_id']
    API_SECRET=json.loads(open(os.path.join(sdll_fldr, "client_secrets.json"), 'r').read())['local']['assignr_client_secret']
    
    auth_url = "https://app.assignr.com/oauth/token"
    #print("Requesting token...")

    payload = {
        "client_id": API_KEY,
        "client_secret": API_SECRET,
        "scope": "read write",
        "grant_type": "client_credentials"
    }

    response = requests.post(auth_url, data=payload)
    result = response.json()  # or response.text if you prefer raw output
    token_res = None
    if 'access_token' in result and result['access_token'] is not None:
        token_res = result['access_token']
        bearer_token_src = os.path.join(sdll_fldr, 'API_BEARER_TOKEN')
        f = open(bearer_token_src, 'w'); f.write(token_res); f.close()
        

    return token_res
    
def assignr_request(url, fn_specs = {}):
    """
    This function makes a request of the assignr API; if the Bearer token is out-of-date or missing a new one will be requested as needed (and stored to a file). 
    """
    res = {'zcSuccess': 0, 'zcError': None}
    if 'headers' not in fn_specs:
        fn_specs['headers'] = None
    if 'payload' not in fn_specs:
        fn_specs['payload'] = None
    if 'request_type' not in fn_specs:
        fn_specs['request_type'] = None
    
    API_KEY=json.loads(open(os.path.join(sdll_fldr, "client_secrets.json"), 'r').read())['local']['assignr_client_id']
    API_SECRET=json.loads(open(os.path.join(sdll_fldr, "client_secrets.json"), 'r').read())['local']['assignr_client_secret']
    
    bearer_token_src = os.path.join(sdll_fldr, 'API_BEARER_TOKEN')
    if os.path.isfile(bearer_token_src):
        BEARER_TOKEN = open(bearer_token_src, 'r').read()
        if BEARER_TOKEN.strip() == "":
            BEARER_TOKEN = get_assignr_token()
    else:
        BEARER_TOKEN = get_assignr_token()
    
    
    if fn_specs['headers'] is None:
        headers = { "accept": "application/json", "authorization": f"Bearer {BEARER_TOKEN}" }
    else:
        headers = fn_specs['headers']
        headers["authorization"] = f"Bearer {BEARER_TOKEN}"
    
    
    if fn_specs['payload'] is not None: # We are using a put to make a change to the DB
        
        print ("URL: %s" % url)
        zc.print_dict(fn_specs)
        if '--no-commit' not in sys.argv:
            if fn_specs['request_type'] == "put":
                response = requests.put(url, data=fn_specs['payload'], headers=headers)
            elif fn_specs['request_type'] == "post":
                #zc.exit("PLD")
                response = requests.post(url, data=fn_specs['payload'], headers=headers)
        
    else:
        response = requests.get(url, headers=headers)
    json_response = json.loads(response.text)
    
    #if fn_specs['request_type'] == "post":
    #    zc.print_dict(json_response)
    #    zc.exit("POST TEST")
        
    # Transfer objects into the res output variable
    for k  in json_response:
        res[k] = json_response[k]
    
    
    # Check if the token used to request the data has expired; if it has, request a new one and replicate the original request
    if 'code' in json_response:
        print ("code: %s" % json_response['code'])
        if json_response['code'] in ["validation_error"]:
            
            print (response.text)
            
        elif json_response['code'] in ["token_invalid", "token_expired"]:
            BEARER_TOKEN = get_assignr_token()
            headers = { "accept": "application/json", "authorization": f"Bearer {BEARER_TOKEN}" }

            response = requests.get(url, headers=headers)
            json_response = json.loads(response.text)
            
            # Transfer objects into the res output variable
            for k  in json_response:
                res[k] = json_response[k]
            #zc.print_dict(json_response)
            
            if 'message' in json_response:
                res['zcError'] = json_response['message']
            
    else:
        res['zcSuccess'] = 1
        
    return res
    
def update_assignr_record_external_ID():
    print ("--update-assignr-record-external-ID")
    # python scratchpad.py --update-assignr-record-external-ID --assignr-ID xxx --db-ID xxx
    assignr_id = int(sys.argv[sys.argv.index('--assignr-ID') + 1])
   
    external_id = int(sys.argv[sys.argv.index('--db-ID') + 1])

    SITE_ID=json.loads(open(os.path.join(sdll_fldr, "client_secrets.json"), 'r').read())['local']['assignr_site_id']
    
    url = f"https://api.assignr.com/api/v2/games/{assignr_id}"
    
    payload = {
        "external_id": external_id
    }
    
    zc.print_dict(payload)
    headers = {"accept": "application/json", "content-type": "application/x-www-form-urlencoded"}
    resp = assignr_request(url, {'payload': payload, 'headers': headers, 'request_type': "put"})
    if resp['zcError'] not in [None, '']:
        msg = "[SDLL ERROR]\n\nTried to update %s from %s to %s\n\nGot this error:\n\n%s" % (update['desc'], update['from'], update['to'], resp['zcError'])
        laxref.telegram_alert(msg)
        zc.send_crash(msg)

#update_assignr_record_external_ID(); sys.exit()
ALERTS = {}    
def update_assignr_games():
    print("--update-assignr-games")
    
    SITE_ID=json.loads(open(os.path.join(sdll_fldr, "client_secrets.json"), 'r').read())['local']['assignr_site_id']
    # Get the data from the respective database/google doc and from the assignr API
    misc = read_master_schedule()
    assignr_games = read_assignr_games()
    
    for g in misc['db_games']:
        
        g['tup'] = (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d%H"))
        g['home_only_tup'] = (g['home_ID'], None, g['game_date'].strftime("%Y%m%d%H"))
        g['away_only_tup'] = (None, g['away_ID'], g['game_date'].strftime("%Y%m%d%H"))
        g['alt_tup'] = (g['away_ID'], g['home_ID'], g['game_date'].strftime("%Y%m%d%H"))
        g['alt_home_only_tup'] = (g['away_ID'], None, g['game_date'].strftime("%Y%m%d%H"))
        g['alt_away_only_tup'] = (None, g['home_ID'], g['game_date'].strftime("%Y%m%d%H"))
        
        g['tup_w_location'] = (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d%H"), g['location'])
        g['home_only_tup_w_location'] = (g['home_ID'], None, g['game_date'].strftime("%Y%m%d%H"), g['location'])
        g['away_only_tup_w_location'] = (None, g['away_ID'], g['game_date'].strftime("%Y%m%d%H"), g['location'])
        g['alt_tup_w_location'] = (g['away_ID'], g['home_ID'], g['game_date'].strftime("%Y%m%d%H"), g['location'])
        g['alt_home_only_tup_w_location'] = (g['away_ID'], None, g['game_date'].strftime("%Y%m%d%H"), g['location'])
        g['alt_away_only_tup_w_location'] = (None, g['home_ID'], g['game_date'].strftime("%Y%m%d%H"), g['location'])
  
    # Create hash values
    for g in assignr_games:
        g['hashed_location'] = laxref.hash_player_name(str(g['location']), {'keep_numbers': 1})
        g['hashed_league'] = laxref.hash_player_name(str(g['league']), {'keep_numbers': 1})
        
        g['game_desc'] = "%s - %s vs %s" % (
            g['game_date'].strftime("%b %d %I:%M %p")
            , "TBD" if g['home_team'] in [None, ''] else g['home_team']
            , "TBD" if g['away_team'] in [None, ''] else g['away_team']
        )
    # Create hash values
    for g in misc['db_games']:
        g['hashed_location'] = laxref.hash_player_name(str(g['location']), {'keep_numbers': 1})
        g['hashed_league'] = laxref.hash_player_name(str(g['league']), {'keep_numbers': 1})
        
    # Set team display names
    for g in misc['db_games']:
        
        g['home_team'] = None
        g['hashed_home_team'] = None
        g['away_team'] = None
        g['hashed_away_team'] = None
        
        if g['home_ID'] is not None:
            db_home = misc['db_teams'].get(g['home_ID'])
            g['home_team'] = db_home['display_name']
            g['hashed_home_team'] = laxref.hash_player_name(str(g['home_team']), {'keep_numbers': 1})
        
        
        if g['away_ID'] is not None:
            db_away = misc['db_teams'].get(g['away_ID']) 
            g['away_team'] = db_away['display_name']
            g['hashed_away_team'] = laxref.hash_player_name(str(g['away_team']), {'keep_numbers': 1})
        
        
        g['game_desc'] = "%s - %s vs %s" % (
            g['game_date'].strftime("%b %d %I:%M %p")
            , "TBD" if g['home_team'] in [None, ''] else g['home_team']
            , "TBD" if g['away_team'] in [None, ''] else g['away_team']
        )
        
    # Add team IDs to assignr games
    for g in assignr_games:
    

        g['home_tup'] = (laxref.hash_player_name(str(g['home_team']), {'keep_numbers': 1}), g['league'])
        g['away_tup'] = (laxref.hash_player_name(str(g['away_team']), {'keep_numbers': 1}), g['league'])
        g['home_is_TBD'] = 0; g['away_is_TBD'] = 0
        g['home_ID'] = None; g['away_ID'] = None
        
        
        if g['home_team'] in ["TBD", ""] or (g['home_team'] is not None and g['home_team'].strip().endswith(" 8")):
            g['home_is_TBD'] = 1
        else:
            tmp_rec = misc['db_teams'].get(g['home_tup'])
            if tmp_rec is not None:
                g['home_ID'] = tmp_rec['team_ID']
            
        if g['away_team'] in ["TBD", ""] or (g['away_team'] is not None and g['away_team'].strip().endswith(" 8")):
            g['away_is_TBD'] = 1
        else:
            tmp_rec = misc['db_teams'].get(g['away_tup']) 
            if tmp_rec is not None:
                g['away_ID'] = tmp_rec['team_ID']
    
    # Create a lookup tup that we can compare against the games in misc['db_games']
    assignr_games_by_league = {}
    assignr_games_by_date = {}
    for g in assignr_games:
        g['tup'] = (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d%H"))
        g['tup_w_location'] = (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d%H"), g['location'])
        g['tup_w_only_location_and_league'] = (g['game_date'].strftime("%Y%m%d%H"), g['location'], g['league'])
        g['tup_w_only_location_and_league_date_only'] = (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d"), g['location'], g['league'])
        g['tup_w_only_league_date_only'] = (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d"), g['league'])
        
        assignr_games_by_league[g['league']] = assignr_games_by_league.get(g['league'], 0) + 1
    
        assignr_games_by_date[g['game_date'].strftime("%Y%m%d")] = assignr_games_by_date.get(g['game_date'].strftime("%Y%m%d"), 0) + 1
    
    
    print ("\n\n10 Random games")
    zc.print_table(assignr_games[0:10], {'keep_keys': ['game_date', 'home_ID', 'away_ID', 'location', 'league', 'found_in_assignr']})
    
    print ("\n\nGames without an umpire")
    dates_without_umpire = [{'dt': z} for z in list(set([y['game_date'].strftime("%Y%m%d") for y in assignr_games if not y['has_umpire']]))]

    dates_without_umpire = sorted(dates_without_umpire, key=lambda x:x['dt'])
    for dt in dates_without_umpire:
        dt['dt_str'] = datetime.strptime(dt['dt'], "%Y%m%d").strftime("%a %b %d").replace(" 0", " ")
        dt['games'] = [z for z in assignr_games if z['game_date'].strftime("%Y%m%d") == dt['dt'] and not z['has_umpire']]
        dt['n_games'] = len(dt['games'])
        
    for dt in dates_without_umpire:
        dt['times'] =  [{'time': z} for z in list(set([y['game_date'].strftime("%I:%M %p") for y in dt['games']]))]
        for tm in dt['times']:
            #if tm['time'].startswith("0") : tm['time'] = tm['time'][1:]
            tm['games'] = [z for z in dt['games'] if z['game_date'].strftime("%I:%M %p") == tm['time']]
            tm['n_games'] = len(tm['games'])
            tm['desc_league_location_list'] = "\n".join([z['desc_league_location'] for z in tm['games']])
            tm['desc_league_location_w_time_list'] = "\n".join([z['desc_league_location_w_time'] for z in tm['games']])
            
    #zc.print_dict(   dates_without_umpire[0]   ) 
    
    print ("\n\nDates w/ Missing Umpires report")
    for dt in dates_without_umpire:
        msg1 =  (f"\n{dt['dt_str']} ({dt['n_games']} games)\n-----------------------")
        if len(dt['times']) > 1:
            for tm in dt['times']:
                tm['desc'] = f"\n\n{tm['time']} ({tm['n_games']} games)\n{tm['desc_league_location_list']}"
                msg1 += tm['desc']
        else:
            if dt['times'][0]['n_games'] == 1:
                tm = dt['times'][0]
                #zc.print_dict(tm)
                tm['desc'] = f"\n\n{tm['desc_league_location_w_time_list']}"
                msg1 += tm['desc']
            else:
                msg1 += f"\n\nAll times are {dt['times'][0]['time']}\n\n"
                
                for tm in dt['times']:
                    tm['desc'] = f"{tm['desc_league_location_list']}"
                    msg1 += tm['desc']
                
        msg1 = msg1.replace("\n0", "\n").replace(" 0", " ").replace(" 1 games", " 1 game").replace("(1 games", "(1 game")
        print (f"\n\n{msg1}")
    if '--just-print' in sys.argv:
        zc.exit("RPO")
    
    
    
    assignr_updates = []
    # Determine if the location and league suggests that this game is one where we need to try and find an umpire via the Assignr app
    misc['db_games_by_league'] = {}
    for i, g in enumerate(misc['db_games']):
        g['tup'] = (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d%H"))
        g['tup_w_location'] = (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d%H"), g['location'])
        g['tup_w_only_location_and_league'] = (g['game_date'].strftime("%Y%m%d%H"), g['location'], g['league'])
        g['tup_w_only_location_and_league_date_only'] = (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d"), g['location'], g['league'])
        g['tup_w_only_league_date_only'] = (g['home_ID'], g['away_ID'], g['game_date'].strftime("%Y%m%d"), g['league'])
        misc['db_games_by_league'][g['league']] = misc['db_games_by_league'].get(g['league'], 0) + 1
        #g['tmp_seq'] = misc['db_games_by_league'].get(g['league'])
    #zc.print_table(sorted([z for z in misc['db_games'] if z['league'] == "BB A"] ,key=lambda x:x['game_date']), {'cutoff1': 200, 'keep_keys': ['tmp_seq', 'game_date', 'game_desc']})
    #zc.exit("BB A")
    
    for g in misc['db_games']:
        
        g['is_hosted_by_non_SDLL'] = 0
        if g['location'].startswith("BCLL Field"):
            g['is_hosted_by_non_SDLL'] = 1
        elif g['location'].startswith("Briar Chapel"):
            g['is_hosted_by_non_SDLL'] = 1
        elif g['location'].startswith("Pittsboro Elementary"):
            g['is_hosted_by_non_SDLL'] = 1
            
        g['is_a_young_umpire_responsibility'] = 0
        if 'is_scrimmage' not in g:
            zc.print_dict_as_table(g); zc.exit("FDdS")
        #if g['ID'] == 1606:
        #    zc.print_dict_as_table(g); print ("xx2886")
        #    zc.exit("GAM")
        if g['umpire_override'] == "Young Umpire":
            g['is_a_young_umpire_responsibility'] = 1
            #if g['is_scrimmage']:
            #    zc.print_dict_as_table(g); zc.exit("UY")
        elif g['location'] == "":
            pass # If no field has been set, then we can't assign an  umpire
        elif not g['is_scrimmage'] and g['league'].strip() in ["SB Rookie", "BB Rookie", "BB A"]:
            if g['location'].startswith("Southern Boundaries"):
                g['is_a_young_umpire_responsibility'] = 1
            elif g['location'].startswith("Herndon"):
                g['is_a_young_umpire_responsibility'] = 1
            elif g['location'].startswith("Cedar Falls"):
                g['is_a_young_umpire_responsibility'] = 1
            elif g['location'].startswith("Northeast District Park"):
                g['is_a_young_umpire_responsibility'] = 0
            elif g['location'].strip() in ['Wrightwood Park', 'Pearsontown Elementary', 'Cresset Christian Academy', 'Shepard Middle School', 'Lowes Grove', 'Lowes Grove SB', 'Sherwood Githens SB', 'Sherwood Githens Middle School', 'Pineywood Park', 'Alston Ridge', 'Parkwood', 'Ephesus Park', 'Northwood HS Softball Field', 'Hillside High School']:
                # Removed 'Northeast District Park' because that's ECLL
                g['is_a_young_umpire_responsibility'] = 1
        elif g['is_scrimmage'] and g['league'].strip() == "All Stars":
            g['is_a_young_umpire_responsibility'] = 1
            
        
        g['umpire_responsibility_is_unclear'] = 1 if ((g['is_scrimmage'] and g['league'] == "All Stars") or not g['is_scrimmage']) and g['location'] not in ['TBD', '', 'Northeast District Park'] and g['league'] in ["All Stars", "SB Rookie", "BB Rookie", "BB A"] and not g['is_hosted_by_non_SDLL'] and not g['is_a_young_umpire_responsibility'] else 0
                
        if g['umpire_responsibility_is_unclear'] and '--ignore-missing-location-games' not in sys.argv:
            print ("League: %s" % (g['league'].strip() in ["SB Rookie", "BB Rookie", "BB A"]))
            print ("Location (%s): %s" % (g['location'], g['location'] in ['Wrightwood Park', 'Cresset Christian Academy', 'Shepard Middle School', 'Lowes Grove', 'Lowes Grove SB', 'Sherwood Githens Middle School', 'Pineywood Park', 'Alston Ridge', 'Northeast District Park', 'Parkwood', 'Ephesus Park', 'Northwood HS Softball Field', 'Hillside High School']))
            
            if '--via-cron' not in sys.argv:
                zc.print_dict_as_table(g);zc.exit("23 - FIELD RESPONSIBILITY ISSUE?")
    # Determine if the games in misc['db_games'] have already been added to assignr
    #zc.print_dict(assignr_games[-1]); print ("There are %d assignr games pulled via API" % len(assignr_games)); zc.exit("GM1")
    assignr_updates_defaultdict=defaultdict(list)
    if '-league' in sys.argv:
        misc['db_games'] = [z for z in misc['db_games'] if z['league'] == sys.argv[ sys.argv.index('-league') + 1]]
   
    if '--ignore-missing-location-games' in sys.argv:
        misc['db_games'] = [z for z in misc['db_games'] if z['location'].strip() == ""]
        
    for g in misc['db_games']:        
        tmp_rec = None
        g['id_match'] = 0
        #print("\n".join([str(z['tup_w_location']) for z in assignr_games]))
        #zc.print_dict_as_table(g); zc.exit("G")
        #zc.exit(g['tup_w_location'] in [z['tup_w_location'] for z in assignr_games])
        if int(g['ID']) in [1606]:
            pass
        elif str(g['ID']) in [str(z['external_id']) for z in assignr_games]:
            tmp_rec = assignr_games[ [str(z['external_id']) for z in assignr_games].index(str(g['ID'])) ]
            g['found_in_assignr'] = 1
            g['id_match'] = 1
            
            if 'assignr_id' in g and g['assignr_id'] is None:
                query = "UPDATE SDLL_Games set assignr_ID=%s where ID=%s;"
                param = [tmp_rec['id'], g['ID']]
                g['assignr_id'] = tmp_rec['id']
                print ("Query %s w/ %s" % (query, param))
                
                cursor = zc.zcursor("SDLL")
                cursor.execute(query, param)
                cursor.commit()
                cursor.close()
            
        elif str(g['assignr_id']) in [str(z['id']) for z in assignr_games]:
            tmp_rec = assignr_games[ [str(z['id']) for z in assignr_games].index(str(g['assignr_id'])) ]
            g['found_in_assignr'] = 1
            g['id_match'] = 1
            
        elif g['tup_w_location'] in [z['tup_w_location'] for z in assignr_games]: # Teams matched between DB and Assignr
            tmp_rec = assignr_games[ [z['tup_w_location'] for z in assignr_games].index(g['tup_w_location']) ]
            g['found_in_assignr'] = 1
            
            if 'assignr_id' in g and g['assignr_id'] is None:
                query = "UPDATE SDLL_Games set assignr_ID=%s where ID=%s;"
                param = [tmp_rec['id'], g['ID']]
                g['assignr_id'] = tmp_rec['id']
                print ("Query %s w/ %s" % (query, param))
                
                cursor = zc.zcursor("SDLL")
                cursor.execute(query, param)
                cursor.commit()
                cursor.close()
        
        elif 0 and g['tup'] in [z['tup'] for z in assignr_games]: # Teams matched between DB and Assignr
            tmp_rec = assignr_games[ [z['tup'] for z in assignr_games].index(g['tup']) ]
            g['found_in_assignr'] = 1
            
            if 'assignr_id' in g and g['assignr_id'] is None:
                query = "UPDATE SDLL_Games set assignr_ID=%s where ID=%s;"
                param = [tmp_rec['id'], g['ID']]
                g['assignr_id'] = tmp_rec['id']
                print ("Query %s w/ %s" % (query, param))
                
                cursor = zc.zcursor("SDLL")
                cursor.execute(query, param)
                cursor.commit()
                cursor.close()
        
        elif g['alt_tup_w_location'] in [z['tup_w_location'] for z in assignr_games]: # Teams matched between DB and Assignr
            tmp_rec = assignr_games[ [z['tup_w_location'] for z in assignr_games].index(g['alt_tup_w_location']) ]
            g['found_in_assignr'] = 1
            
            if 'assignr_id' in g and g['assignr_id'] is None:
                query = "UPDATE SDLL_Games set assignr_ID=%s where ID=%s;"
                param = [tmp_rec['id'], g['ID']]
                g['assignr_id'] = tmp_rec['id']
                print ("Query %s w/ %s" % (query, param))
                
                cursor = zc.zcursor("SDLL")
                cursor.execute(query, param)
                cursor.commit()
                cursor.close()
        
        elif 0 and g['alt_tup'] in [z['tup'] for z in assignr_games]: # Teams matched between DB and Assignr
            tmp_rec = assignr_games[ [z['tup'] for z in assignr_games].index(g['alt_tup']) ]
            g['found_in_assignr'] = 1
            
            if 'assignr_id' in g and g['assignr_id'] is None:
                query = "UPDATE SDLL_Games set assignr_ID=%s where ID=%s;"
                param = [tmp_rec['id'], g['ID']]
                g['assignr_id'] = tmp_rec['id']
                print ("Query %s w/ %s" % (query, param))
                
                cursor = zc.zcursor("SDLL")
                cursor.execute(query, param)
                cursor.commit()
                cursor.close()
        
        elif g['home_only_tup'] in [z['tup'] for z in assignr_games]: # Away team needs to be updated in assignr
            tmp_rec = assignr_games[ [z['tup'] for z in assignr_games].index(g['home_only_tup']) ]
            g['found_in_assignr'] = 1
            if tmp_rec['away_team'] != "TBD" or g['away_team'] not in [None, '']:
            
                
                update = {'db_game_ID': g['ID'], 'seq': len(assignr_updates) + 1, 'tag': 'away_team_only', 'league': tmp_rec['league'], 'game_desc': tmp_rec['game_desc'], 'location': tmp_rec['location'], 'assignr_id': tmp_rec['id'], 'desc': 'Update Away Team', 'field': 'away_team', 'from': tmp_rec['away_team'], 'to': g['away_team']}
                assignr_updates.append(update)
                
                
                if 0 and "UPDATE THE AWAY TEAM" not in ALERTS and '-quiet' not in sys.argv:
                    ALERTS["UPDATE THE AWAY TEAM"] = 1
                    msg = f"Found a game in assignr where the home team was specified, but the away team was not; add {g['away_team']} as the away team to game with assignr_id={tmp_rec['id']}"
                    laxref.telegram_alert(msg)
                    print (msg)
                
        elif g['alt_home_only_tup'] in [z['tup'] for z in assignr_games]: # Away team needs to be updated in assignr
            tmp_rec = assignr_games[ [z['tup'] for z in assignr_games].index(g['alt_home_only_tup']) ]
            g['found_in_assignr'] = 1
            if tmp_rec['away_team'] != "TBD" or g['away_team'] not in [None, '']:
            
                update = {'db_game_ID': g['ID'], 'seq': len(assignr_updates) + 1, 'tag': 'away_team_only', 'league': tmp_rec['league'], 'game_desc': tmp_rec['game_desc'], 'location': tmp_rec['location'], 'assignr_id': tmp_rec['id'], 'desc': 'Update Away Team', 'field': 'away_team', 'from': tmp_rec['away_team'], 'to': g['away_team']}
                assignr_updates.append(update)
                
                
                if 0 and "UPDATE THE AWAY TEAM" not in ALERTS and '-quiet' not in sys.argv:
                    ALERTS["UPDATE THE AWAY TEAM"] = 1
                    msg = f"Found a game in assignr where the home team was specified, but the away team was not; add {g['away_team']} as the away team to game with assignr_id={tmp_rec['id']}"
                    laxref.telegram_alert(msg)
                    print (msg)
                
        elif g['away_only_tup'] in [z['tup'] for z in assignr_games]: #Home team needs to be updated in assignr
            
            tmp_rec = assignr_games[ [z['tup'] for z in assignr_games].index(g['away_only_tup']) ]
            if tmp_rec['home_team'] != "TBD" or g['home_team'] not in [None, '']:
                g['found_in_assignr'] = 1
                
                
                update = {'db_game_ID': g['ID'], 'seq': len(assignr_updates) + 1, 'tag': 'home_team_only', 'league': tmp_rec['league'], 'game_desc': tmp_rec['game_desc'], 'location': tmp_rec['location'], 'assignr_id': tmp_rec['id'], 'desc': 'Update Home Team', 'field': 'home_team', 'from': tmp_rec['home_team'], 'to': g['home_team']}
                assignr_updates.append(update)
                
                if 0 and "UPDATE THE HOME TEAM" not in ALERTS and '-quiet' not in sys.argv:
                    ALERTS["UPDATE THE HOME TEAM"] = 1
                    msg = f"Found a game in assignr where the away team was specified, but the home team was not; add {g['home_team']} as the home team to game with assignr_id={tmp_rec['id']}"
                    laxref.telegram_alert(msg)
                    print (msg)
                
        elif g['alt_away_only_tup'] in [z['tup'] for z in assignr_games]: #Home team needs to be updated in assignr
            tmp_rec = assignr_games[ [z['tup'] for z in assignr_games].index(g['alt_away_only_tup']) ]
            g['found_in_assignr'] = 1
            if tmp_rec['home_team'] != "TBD" or g['home_team'] not in [None, '']:
            
                update = {'db_game_ID': g['ID'], 'seq': len(assignr_updates) + 1, 'tag': 'home_team_only', 'league': tmp_rec['league'], 'game_desc': tmp_rec['game_desc'], 'location': tmp_rec['location'], 'assignr_id': tmp_rec['id'], 'desc': 'Update Home Team', 'field': 'home_team', 'from': tmp_rec['home_team'], 'to': g['home_team']}
                assignr_updates.append(update)
                
                if 0 and "UPDATE THE HOME TEAM" not in ALERTS and '-quiet' not in sys.argv:
                    ALERTS["UPDATE THE HOME TEAM"] = 1
                    msg = f"Found a game in assignr where the away team was specified, but the home team was not; add {g['home_team']} as the home team to game with assignr_id={tmp_rec['id']}"
                    laxref.telegram_alert(msg)
                    print (msg)
                
        if tmp_rec is None: # No match found; probably need to create a record in assignr
            
            if g['assignr_id'] is None and (datetime.now() - timedelta(days=0)) <= g['game_date'] <= (datetime.now() + timedelta(days=150)):
                
                
                add_it = 0
                if g['league'] in ["SB Rookie", "BB Rookie", "BB A"] and not g['is_hosted_by_non_SDLL'] and g['is_a_young_umpire_responsibility']:
                    add_it = 1
                elif g['umpire_override'] == "Young Umpire":
                    add_it = 1
                    
                if add_it:
                    if '--skip-add-games' not in sys.argv and g['ID'] not in [1606]:
                        #print ([z['tup_w_only_location_and_league'] for z in assignr_games])
                        #print (g['tup_w_only_location_and_league'])
                        update = {'db_game_ID': g['ID'], 'seq': len(assignr_updates) + 1, 'tag': 'add_game', 'league': g['league'], 'home_ID': g['home_ID'], 'away_ID': g['away_ID'], 'game_desc': g['game_desc'], 'location': g['location'], 'assignr_id': None, 'desc': 'Add Game', 'field': 'all', 'from': "[empty]", 'to': "all", 'game_obj': json.loads(json.dumps(g, default=zc.json_handler))}
                        if g['tup_w_only_location_and_league'] in [z['tup_w_only_location_and_league'] for z in assignr_games]:
                            update['location_match'] = "YES"
                            update['tag'] = "confirm_teams"
                            update['desc'] = "Location Match / Confirm Teams"
                            
                        assignr_updates.append(update)
                elif g['league'] in ["BB AA"] and g['game_date'].strftime("%Y%m%d") == "20250601" and not g['is_hosted_by_non_SDLL'] and g['is_a_young_umpire_responsibility'] and "--add-AA" in sys.argv:
                    if '--skip-add-games' not in sys.argv:
                    
                        update = {'db_game_ID': g['ID'], 'seq': len(assignr_updates) + 1, 'tag': 'add_game', 'league': g['league'], 'home_ID': g['home_ID'], 'away_ID': g['away_ID'], 'game_desc': g['game_desc'], 'location': g['location'], 'assignr_id': None, 'desc': 'Add Game', 'field': 'all', 'from': "[empty]", 'to': "all", 'game_obj': json.loads(json.dumps(g, default=zc.json_handler))}
                        if g['tup_w_only_location_and_league'] in [z['tup_w_only_location_and_league'] for z in assignr_games]:
                            update['location_match'] = "YES"
                            update['tag'] = "confirm_teams"
                            update['desc'] = "Location Match / Confirm Teams"
                            update['desc'] = "confirm_teams"
                        
                        assignr_updates.append(update)
            
        else: # Record found; do we need to update time/location
            if tmp_rec['game_date'] is None or g['game_date'].strftime("%Y%m%d%H%M") != tmp_rec['game_date'].strftime("%Y%m%d%H%M"):
                
                just_time_change = 1 if g['game_date'].strftime("%Y%m%d") == tmp_rec['game_date'].strftime("%Y%m%d") else 0
                if just_time_change: # It's only the time of the game that is changing; not the date
                    update = {'db_game_ID': g['ID'], 'seq': len(assignr_updates) + 1, 'tag': 'time_change_only', 'league': tmp_rec['league'], 'game_desc': tmp_rec['game_desc'], 'location': tmp_rec['location'], 'assignr_id': tmp_rec['id'], 'desc': 'Update Game Date', 'field': 'start_time', 'from': tmp_rec['game_date'], 'duration_in_hours': g['duration_in_hours'], 'to': g['game_date']}
                else:
                    update = {'db_game_ID': g['ID'], 'seq': len(assignr_updates) + 1, 'tag': 'date_and_time_change', 'league': tmp_rec['league'], 'game_desc': tmp_rec['game_desc'], 'location': tmp_rec['location'], 'assignr_id': tmp_rec['id'], 'desc': 'Update Game Date', 'field': 'start_time', 'from': tmp_rec['game_date'], 'duration_in_hours': g['duration_in_hours'], 'to': g['game_date']}
                    
                assignr_updates.append(update)
                
                if "UPDATE THE GAMEDATE" not in ALERTS and '-quiet' not in sys.argv:
                    ALERTS["UPDATE THE GAMEDATE"] = 1
                    
            
            
                    msg = "Found a game in assignr where the game time needs to be updated; set time={} for game with assignr_id={} (it was {})".format(g['game_date'].strftime("%b %d %I:%M %p"), tmp_rec['id'], tmp_rec['game_date'].strftime("%b %d %I:%M %p"))
                    laxref.telegram_alert(msg)
                    print (msg)
                    
            if tmp_rec['hashed_location'] in ['', None] or g['hashed_location'] != tmp_rec['hashed_location']:
                
                update = {'db_game_ID': g['ID'], 'seq': len(assignr_updates) + 1, 'tag': 'location_update', 'game_desc': tmp_rec['game_desc'], 'location': tmp_rec['location'], 'assignr_id': tmp_rec['id'], 'desc': 'Update Location', 'field': 'venue_name', 'from': tmp_rec['location'], 'to': g['location']}
                assignr_updates.append(update)
                
                if "UPDATE THE LOCATION" not in ALERTS and '-quiet' not in sys.argv:
                    ALERTS["UPDATE THE LOCATION"] = 1
                    msg = f"Found a game in assignr where the location needs to be updated; should be location={g['location']} (it was location={tmp_rec['hashed_location']}) for game with assignr_id={tmp_rec['id']}"
                    laxref.telegram_alert(msg)
                    print (msg)
    for update in assignr_updates:
        assignr_updates_defaultdict[update['desc']].append(update)
        if 'location_match' not in update:
            update['location_match'] = ""
            
    # To see the games that have been identified as needing to be added...
    #zc.print_table([z for z in assignr_updates if z['desc'] in ['Add Game']]); zc.exit("ADD GAMES?")
    
    
    #zc.print_table([z for z in misc['db_games'] if z['assignr_id'] is not None][-10:], {'keep_keys': ['game_desc', 'assignr_id', 'id_match']})
        
    w_umpire_responsibility_is_unclear = [z for z in misc['db_games'] if z['umpire_responsibility_is_unclear']]
    n_w_umpire_responsibility_is_unclear = len(w_umpire_responsibility_is_unclear)
    if n_w_umpire_responsibility_is_unclear > 0:
        msg = "There are {} games where the umpire responsibility is not clear; likely because of a new field; run this to see the list {}".format(n_w_umpire_responsibility_is_unclear, zc.get_original_script_command().replace(".py", ".py  --exit-after-unclear-responsibility"))
        
        tmp_games = [z for z in misc['db_games'] if z['umpire_responsibility_is_unclear']]
        
        
        if tmp_games != []:
            if datetime.now() > datetime(2026, 6, 6):
                
                zc.send_crash(msg)
                laxref.telegram_alert(msg)
                print (msg)
            
            
            print ("List of games where UMPIRE Responsibility is unclear")
            zc.print_table(tmp_games, {'keep_keys': ['game_date', "ID", "db_game_ID", 'home_ID', 'away_ID', 'location', 'league', 'found_in_assignr']})
            
            
            
            if '--exit-after-unclear-responsibility' in sys.argv:
                zc.exit("RESPONSIBLE?")
     
    print ("\n\nLast 10 games found in the misc['db_games'] list")
    zc.print_table([z for z in misc['db_games'] if z['game_date'] > datetime.now()][-10:], {'keep_keys': ['game_date', 'home_ID', 'away_ID', 'location', 'league', 'found_in_assignr']})
    
    print ("\nAssignr DB Games by League")
    zc.print_table([{'League': k, 'Assignr DB Count': z, 'SDLL DB Count (incl plachldrs)': misc['db_games_by_league'].get(k)} for k, z in assignr_games_by_league.items()])
    
    
    #print ("\nAssignr DB Games by Date")
    #zc.print_dict_as_table(assignr_games_by_date)
    if '--change-desc' in sys.argv:
        assignr_updates = [z for z in assignr_updates if z['desc'] == sys.argv[sys.argv.index('--change-desc') + 1]]
        
    n_assignr_updates = len(assignr_updates)
    if n_assignr_updates > 0:
        print ("\n\nUpdates to be made to Assignr game records")
    
        zc.print_table(assignr_updates, {'cutoff*': 20, 'cutoff_desc': 30, 'cutoff_game_desc': 75, 'cutoff_assignr_id': 12, 'cutoff_tag': 16, 'cutoff_db_game_ID': 12, 'cutoff_seq': 6, 'cutoff_location': 30, 'ignore_keys': ['game_obj', 'field']})
        
        print ("\nAssignr Updates by Type")
        assignr_updates_defaultdict = dict(sorted(assignr_updates_defaultdict.items()))
        for k in assignr_updates_defaultdict:
            print ("{:<30}{:<30}".format(k, "{:,} update(s)".format(len(assignr_updates_defaultdict[k]))))
           

        if '--just-notify' in sys.argv:
            resp = "n"
        else:
            resp = input("\nGo ahead with updates (y/n)? ")
        if resp != "y":
            zc.exit("EXITING...")
        for update in assignr_updates:
            if update['tag'] == "location_update":
                url = f"https://api.assignr.com/api/v2/games/{update['assignr_id']}"
                payload = { "venue_name": update['to'] }
                headers = {"accept": "application/json", "content-type": "application/x-www-form-urlencoded"}
                resp = assignr_request(url, {'payload': payload, 'headers': headers, 'request_type': "put"})
                if resp['zcError'] not in [None, '']:
                    msg = "[SDLL ERROR]\n\nTried to update %s from %s to %s\n\nGot this error:\n\n%s" % (update['desc'], update['from'], update['to'], resp['zcError'])
                    laxref.telegram_alert(msg)
                    zc.send_crash(msg)
                    
        for update in assignr_updates:
            if update['tag'] == "time_change_only":
                url = f"https://api.assignr.com/api/v2/games/{update['assignr_id']}"
                #zc.print_dict(update); zc.exit("UPD")
                tmp_end_time = update['to'] + timedelta(seconds=update['duration_in_hours'] * 3600)
                payload = { "localized_time": update['to'].strftime("%H:%M:%S"), "user_end_time_formatted": tmp_end_time.strftime("%H:%M:%S") }
                headers = {"accept": "application/json", "content-type": "application/x-www-form-urlencoded"}
                print (json.dumps(payload, indent=1))
                resp = assignr_request(url, {'payload': payload, 'headers': headers, 'request_type': "put"})
                if resp['zcError'] not in [None, '']:
                    msg = "[SDLL ERROR]\n\nTried to update %s from %s to %s\n\nGot this error:\n\n%s" % (update['desc'], update['from'], update['to'], resp['zcError'])
                    laxref.telegram_alert(msg)
                    zc.send_crash(msg)
                    
            elif update['tag'] == "date_and_time_change":
                url = f"https://api.assignr.com/api/v2/games/{update['assignr_id']}"
                #zc.print_dict(update); zc.exit("UPD")
                tmp_end_time = update['to'] + timedelta(seconds=update['duration_in_hours'] * 3600)
                payload = { "localized_date": update['to'].strftime("%Y-%m-%d"), "localized_time": update['to'].strftime("%H:%M:%S"), "user_end_time_formatted": tmp_end_time.strftime("%H:%M:%S") }
                headers = {"accept": "application/json", "content-type": "application/x-www-form-urlencoded"}
                print (json.dumps(payload, indent=1))
                resp = assignr_request(url, {'payload': payload, 'headers': headers, 'request_type': "put"})
                if resp['zcError'] not in [None, '']:
                    msg = "[SDLL ERROR]\n\nTried to update %s from %s to %s\n\nGot this error:\n\n%s" % (update['desc'], update['from'], update['to'], resp['zcError'])
                    laxref.telegram_alert(msg)
                    zc.send_crash(msg)
                    
        for update in assignr_updates:
            if update['tag'] == "add_game":
                url = f"https://api.assignr.com/api/v2/sites/{SITE_ID}/games"
                game_obj = update['game_obj']
                game_obj['game_date'] = datetime.strptime(game_obj['game_date'], "%Y-%m-%d %H:%M:%S")
                #zc.print_dict(game_obj)
                
                payload = {
                    "venue_name": game_obj['location'],
                    "pattern_name": "1 umpire",
                    "is_public": "y",
                    "home_team_name": "TBD" if game_obj['home_team'] in [None, ''] else game_obj['home_team'],
                    "away_team_name": "TBD" if game_obj['away_team'] in [None, ''] else game_obj['away_team'],
                    "localized_date": game_obj['game_date'].strftime("%Y-%m-%d"),
                    "localized_time": game_obj['game_date'].strftime("%H:%M:%S"),
                    "age_group_name": game_obj['league'],
                    "external_id": game_obj['ID']
                }
                
                if None not in [game_obj['game_date'], game_obj['duration_in_hours']]: # Then we can add the end date
                    payload["user_end_time_formatted"] = (game_obj['game_date'] + timedelta(seconds=game_obj['duration_in_hours']*3600)).strftime("%H:%M:%S")
                #zc.print_dict(payload)
                headers = {"accept": "application/json", "content-type": "application/x-www-form-urlencoded"}
                resp = assignr_request(url, {'payload': payload, 'headers': headers, 'request_type': "post"})
                if resp['zcError'] not in [None, '']:
                    msg = "[SDLL ERROR]\n\nTried to update %s from %s to %s\n\nGot this error:\n\n%s" % (update['desc'], update['from'], update['to'], resp['zcError'])
                    laxref.telegram_alert(msg)
                    zc.send_crash(msg)
    else:
        print ("No updates required")
    print ("Done with fn.update_assignr_games...")
    
def add_descriptions_for_each_assignr_game(all_games, fn_specs):
    """
    To support sending notifications about games, we need to create a description with the pertinent information so that it can be included in a list
    """
    for g in all_games:
        g['desc_league_location'] = f"{g['league']} @ {g['location']}"
        tmp_time_str = g['game_date'].strftime("%I:%M %p")
        g['desc_league_location_w_time'] = f"{g['league']} @ {tmp_time_str} ({g['location']})"
        g['desc_league_time_location'] = f"{g['league']} @ {tmp_time_str} ({g['location']})"
        
    return all_games
    
def read_assignr_games(all_games=0):
    print("--read-assignr-games")
    # python scratchpad.py --update-games --update-assignr-games
    # python scratchpad.py --update-games --update-assignr-games --no-commit
    
    SITE_ID=json.loads(open(os.path.join(sdll_fldr, "client_secrets.json"), 'r').read())['local']['assignr_site_id']
    umpire_emails = {}
    
    #url = "https://api.assignr.com/api/v2/current_account/games?page=1&limit=50"
    url = "https://api.assignr.com/api/v2/current_account/leagues"

    year = datetime.now().year
    if '-year' in sys.argv:
        year = int(sys.argv[sys.argv.index('-year') + 1])
    
    start_dt = datetime.now().strftime("%Y-%m-%d")
    if all_games:
        if IS_SPRING:
            start_dt = datetime(year, 1, 1)
        else:
            start_dt = datetime(year, 8, 1)
    end_dt = (datetime.now() + timedelta(days=150)).strftime("%Y-%m-%d")
    #url = f"https://api.assignr.com/api/v2/sites/{SITE_ID}/leagues?page=1&limit=50"
    
    n_pages = 5; n_limit = 50
    last_n = None
    n_pages_requested = 0
    
    all_games = []
    while n_pages_requested < 5 and (last_n is None or last_n == n_limit):
        n_pages_requested += 1
        url = f"https://api.assignr.com/api/v2/sites/{SITE_ID}/games?page={n_pages_requested}&limit={n_limit}&search[start_date]={start_dt}&search[end_date]={end_dt}"
        
        """url = "https://api.assignr.com/api/v2/users/id"

headers = {"accept": "application/json"}

response = requests.get(url, headers=headers)

print(response.text)"""



        
        
        try:
            
            json_response = assignr_request(url)
            
            games = json_response['_embedded']['games']
            #zc.exit(json.dumps(games, indent=1))
            
            # Convert start time string into game_date datetime value
            for g in games:
                g['game_date'] = None; g['days_until_game'] = None
                try:
                    
                    g['game_date'] = datetime.strptime(g['start_time'][0:19], "%Y-%m-%dT%H:%M:%S")
                    g['days_until_game'] = (g['game_date'] - datetime.now()).total_seconds() / 3600 / 24
                except Exception:
                    if 'DATE_CONV' not in ALERTS and '-quiet' not in sys.argv:
                        ALERTS['DATE_CONV'] = 1
                        msg = f"[SDLL ERROR]\n\nFailed to convert a start_time string ({g['start_time']}), into a valid datetime"
                        laxref.telegram_alert(msg)
                        zc.send_crash(msg)
                        print (msg)
                        
                    
            for g in games:
                g['location'] = None
                g['umpires'] = []
                g['umpires_w_ID'] = []
                g['umpire_str'] = ""
                g['has_umpire'] = 0
                g['league'] = None
                if 'age_group' in g:
                    g['league'] = g['age_group']
                if '_embedded' in g:
                    if 'venue' in g['_embedded'] and g['_embedded']['venue'] is not None:
                        if 'name' in g['_embedded']['venue']:
                            g['location'] = g['_embedded']['venue']['name']
                    if 'assignments' in g['_embedded'] and g['_embedded']['assignments'] is not None:
                        accepted_assignments = [z for z in g['_embedded']['assignments'] if z['accepted'] in [True, 'True']]
                        unaccepted_assignments = [z for z in g['_embedded']['assignments'] if z['accepted'] not in [True, 'True']]
                        if len(accepted_assignments) > 0:
                            #zc.print_dict(accepted_assignments)
                            if 'MULTIPLEACCEPTED' not in ALERTS and len(accepted_assignments) > 1 and '-quiet' not in sys.argv:
                                ALERTS['MULTIPLEACCEPTED'] = 1
                                laxref.telegram_alert("[SDLL ALERT]\n\nFound multiple accepted assignments for a single game")
                            
                            for tmp_ump in accepted_assignments:
                                #zc.print_dict(tmp_ump['_embedded']['official'])
                                if '_embedded' in tmp_ump and tmp_ump['_embedded'] is not None:
                                    if 'official' in tmp_ump['_embedded'] and tmp_ump['_embedded']['official'] is not None:
                                        g['umpires'].append(f"{tmp_ump['_embedded']['official']['first_name']} {tmp_ump['_embedded']['official']['last_name']}")
                                        UMPIRE_IDS_BY_NAME[f"{tmp_ump['_embedded']['official']['first_name']} {tmp_ump['_embedded']['official']['last_name']}"] = tmp_ump['_embedded']['official'].get('id')
                                        d = {'name': f"{tmp_ump['_embedded']['official']['first_name']} {tmp_ump['_embedded']['official']['last_name']}", "id": tmp_ump.get('id'), 'account_id': tmp_ump.get('account_id')}
                                        g['umpires_w_ID'].append(d)
                            g['umpire_str'] = zc.list_to_sentence(g['umpires'])
                            g['has_umpire'] = 1
                            
                        elif len(accepted_assignments) > 1:
                            #zc.print_dict(accepted_assignments)
                            if 'MULTIPLEACCEPTED' not in ALERTS and '-quiet' not in sys.argv:
                                ALERTS['MULTIPLEACCEPTED'] = 1
                                laxref.telegram_alert("[SDLL ALERT]\n\nFound multiple accepted assignments for a single game")
                            
            zc.print_table(games, {'cutoff*': 20, 'keep_keys': ['start_time', 'league', 'home_team', 'away_team', 'league', 'status', 'user_defined_id', 'external_id', 'id', 'location', 'umpire_str']})
            #zc.print_dict(games[0])
            #zc.print_dict(games[0]['_embedded'])
        except Exception:
            msg = "Could not read JSON response into JSON object\n\n[url requested] %s\n\n[error] %s" % (url, traceback.format_exc())
            print(msg)
            
            
        all_games += games
        
        last_n = len(games)

    all_games = add_descriptions_for_each_assignr_game(all_games, {})
    
    in_period_games_without_umpire = [z for z in all_games if not z['has_umpire'] and z['days_until_game'] < 5.25]
    n_without_umpire = len(in_period_games_without_umpire)
    if n_without_umpire > 0:
        tmp_json = json.dumps(in_period_games_without_umpire, default=zc.json_handler, indent=1)
        msg = f"[SDLL ISSUE]\n\nThere are {n_without_umpire} games that do not have an umpire in the next 10 days\n\n{tmp_json}"
    else:
        msg = f"[SDLL HOORAY]\n\nThere are {n_without_umpire} games that do not have an umpire in the next 10 days"
    print (msg)
    if '-quiet' not in sys.argv and '--via-cron' in sys.argv and '--send-umpire-day-of-email' not in sys.argv and ('--report-missing-umpires' in sys.argv or datetime.now().hour == 15):
        pass # laxref.telegram_alert(msg)
        
    return all_games
    
try:
    if datetime.now().strftime("%Y%m%d") in ['20260615']:
        sys.exit()
    if '--show-assignr-counts-by-umpires' in sys.argv:
        show_assignr_counts_by_umpires(); sys.exit()
    elif '--retrieve-umpire-feedback-from-standings-google-sheets' in sys.argv:
        retrieve_umpire_feedback_from_standings_google_sheets(); sys.exit()
    elif "--send-umpire-day-of-email" in sys.argv:
        send_umpire_day_of_email(); sys.exit()
    elif '--compile-schedule-changes' in sys.argv:
        compile_schedule_changes(); sys.exit()
    elif '--read-master-schedule' in sys.argv:
        read_master_schedule(); sys.exit()
    elif '--read-assignr-games' in sys.argv or '--read-assignr' in sys.argv:
        assignr_games = read_assignr_games(); sys.exit()
    elif '--update-assignr-games' in sys.argv or '--update-assignr' in sys.argv:
        update_assignr_games(); sys.exit()
    elif '--data-checkups' in sys.argv:
        data_checkups(); sys.exit()
    elif "--update-assignr-record-external-ID" in sys.argv:
        update_assignr_record_external_ID(); sys.exit()
    elif "--send-umpire-upcoming-schedule-email" in sys.argv:
        send_umpire_upcoming_schedule_email(); sys.exit()
    elif "--check-for-all-star-announcement" in sys.argv:
        check_for_all_star_announcement(); sys.exit()

except Exception as e:


    print (traceback.format_exc())

    if '-quiet' not in sys.argv:
        zc.send_crash(zc.format_error_traceback(traceback.format_exc()), bot_token)
        
    err_msg = traceback.format_exc()
    
    alert_me = 1 if '--via-cron' in sys.argv else 0
    
    # These reflect mission-critical scripts where an error needs to be alerted via Telegram (i.e. high priority) rather than just logged via an email report (lower priority)
    arg_flags_to_alert_on = []
    for z in arg_flags_to_alert_on:
        if z in sys.argv:
            alert_me = 1
        
    if "NoneType has no" in err_msg:
        alert_me = 0
    
    if alert_me and '-quiet' not in sys.argv:
        laxref.telegram_alert(err_msg + "\n\n" + zc.get_original_script_command())
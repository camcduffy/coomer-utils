import getpass
import requests
import urllib.request
from urllib.request import urlretrieve
from progressbar import ProgressBar, Percentage, Bar, AdaptiveETA, DataSize, FileTransferSpeed
import shutil
import re
import sys
import json
import os
import ssl
from datetime import date
from datetime import datetime
from datetime import timedelta
import time
import argparse
from enum import Enum
import signal
from concurrent.futures import ThreadPoolExecutor

class CKUtils:
    # Constructor
    def __init__(self, site, service, username="", password=""):

        self.__site = site
        self.__service = service
        self.__session_token = "anonymous"

        credentialsData = None
        headers = None
        
        if username != "" and password != "":
            # Get a session token
            credentialsData = "username=" + username + "&password=" + password
            headers = {"Content-type" : "application/x-www-form-urlencoded"}

            response = requests.post("https://" + site + "/account/login", data=credentialsData, allow_redirects=False, headers=headers)

            if response.status_code == 302:
                self.__session_token = re.sub(r'.*session=([^;]*).*', r'\1', response.headers["Set-Cookie"])
            else:
                print("Error : " + str(response.status_code))
                sys.exit(2)

    # Call API
    def call_get_API(self, uri):
        request_url = "https://" + self.__site + uri
        #print(request_url)
        response = requests.get(request_url, cookies={'session': self.__session_token})
        return response.content
            
    # Get API version
    def get_API_version(self):
        response = requests.get("https://" + self.__site + "/api/v1/app_version")
        if response.status_code != 200:
            print("Site '" + self.__site + "' not available : " + str(response.status_code))
            sys.exit(1)
        return response.text

    class File_type(Enum):
        VIDEO = "video"
        IMAGE = "image"
        ARCHIVE = "archive"
        DOCUMENT = "document"
        OTHER = "other"
        
        def __str__(self):
            return self.value

    FAVORITES = "--FAVORITES--"

    # Get file type
    def __get_file_type(self, file):
        file_name = file["name"]
        if file_name.lower().endswith(".m4v") or file_name.lower().endswith(".mp4"):
            return CKUtils.File_type.VIDEO
        elif file_name.lower().endswith(".jpg") or file_name.lower().endswith(".jpeg") or \
             file_name.lower().endswith(".png") or file_name.lower().endswith(".gif"):
            return CKUtils.File_type.IMAGE
        elif file_name.lower().endswith(".rar") or file_name.lower().endswith(".zip") or \
             file_name.lower().endswith(".7z"):
            return CKUtils.File_type.ARCHIVE
        elif file_name.lower().endswith(".pdf"):
            return CKUtils.File_type.DOCUMENT
        else:
            return CKUtils.File_type.OTHER

    # Get file full path
    def __get_file_full_path(self, file):
        return "https://" + self.__site + "/data" + file["path"]

    # Get post clean post title
    def __get_post_title(self, post):
        post_title = post["title"]
        
        # If post title is empty, use post ID
        if post_title == None or post_title == "":
            post_title = post["id"]
        
        # Suppress special characters (transform / in -)
        return re.sub("[^A-Za-z0-9 '-_]+", '', re.sub("/", "-", post_title))

    # Get post files
    def __get_post_files(self, post):
        post_files = []
        if post["file"]:
            post_files.append(post["file"])
            
        for attachment in post["attachments"]:
            post_files.append(attachment)
            
        return post_files

    # Get user's post
    # Arguments :
    # - user_id : user ID
    # - from_date : list from this date (all posts if omitted)
    # - from_post_id : list from post ID (all posts if omitted)
    #
    # Returns list of posts
    def __get_user_posts(self, user_id, from_date=None, to_date=None, from_post_id=None, to_post_id=None, reverse_order=False):
        post_offset = 0;
        post_list = []
        
        # Loop all the posts
        while True:
        
            if user_id != CKUtils.FAVORITES:
                posts = json.loads(ckutils.call_get_API("/api/v1/" + self.__service + "/user/" + user_id + "?o=" + str(post_offset)))
            else:
                # No pagination
                if post_offset == 0:
                    posts = json.loads(ckutils.call_get_API("/api/v1/account/favorites?type=post"))
                else:
                    posts = []
            
            # No more posts, exit function
            if len(posts) == 0:
                return post_list
                    
            for post in posts:
                post_added_date = datetime.fromisoformat(post["added"])
                post_title = self.__get_post_title(post)
                post_id = post["id"]
                
                # Skip posts until we find the first post matching the date or/and the post ID
                if (from_post_id and (from_post_id != post_id)) or ((from_date and (from_date < post_added_date))):
                    continue
                    
                if (to_post_id and (to_post_id == post_id)) or ((to_date and (to_date > post_added_date))):
                    return post_list
                    
                # From now, display all the files
                from_post_id = None
                from_date = None
                
                if not reverse_order:
                    post_list.append(post)
                else:
                    post_list.insert(0, post)
                    
            # Load next 50 posts
            post_offset += 50


    # Get user's files.
    # Arguments :
    # - user_id : user ID
    # - file_type : File_type (all if omitted)
    # - from_date : list from this date (all posts if omitted)
    # - from_post_id : list from post ID (all posts if omitted)
    # - get_size : get file size (False by default)
    #
    # Returns list of files: [{"name": "string", "path": "string", "type": "string", "size": int, "post_id": string, "post_title": "string"}]
    def __get_user_files(self, user_id, file_type=None, from_date=None, to_date=None, from_post_id=None, to_post_id=None, get_size=False, reverse_order=False):
        post_offset = 0;
        file_list = []
        file_full_path_list = []
        
        # Loop all the posts
        post_list = self.__get_user_posts(user_id, from_date, to_date, from_post_id, to_post_id, reverse_order)
        
        for post in post_list:
            post_title = self.__get_post_title(post)
            post_id = post["id"]
            
            for file in self.__get_post_files(post):
                post_file_type = self.__get_file_type(file)
                
                # Skip file with wrong type
                if file_type != None and (file_type != post_file_type):
                    continue
                
                file_info = {}
                file_info["name"] = file["name"]
                file_info["full_path"] = self.__get_file_full_path(file)
                file_info["type"] = post_file_type
                file_info["post_id"] = post["id"]
                file_info["post_title"] = post_title
                file_info["added"] = post["added"]
                file_info["published"] = post["published"]
                
                # Get file size
                if get_size:
                    response = requests.request('HEAD', self.__get_file_full_path(file))
                    size = response.headers["Content-Length"]
                    file_info["size"] = int(size)
                
                # Avoid doublons
                if not file_info["full_path"] in file_full_path_list:
                    file_list.append(file_info)
                    file_full_path_list.append(file_info["full_path"] )
                
        return file_list

    # Check API
    def __check_user_exists(self, user):
        request_url = "https://" + self.__site + '/api/v1/' + self.__service + '/user/' + user + '/profile'
        #print(request_url)
        
        nbTries = 0
        
        while nbTries < 3:
            response = requests.head(request_url)
            response = requests.get(request_url)

            if response.status_code == 200:
                return True
            elif response.status_code == 404:
                return False
            else:
                nbTries += 1
                
            time.sleep(3)
            
        return False


    # Display user's files.
    # Arguments :
    # - user_id : user ID
    # - file_type : File_type (all if omitted)
    # - from_date : list from this date (all posts if omitted)
    # - from_post_id : list from post ID (all posts if omitted)
    # - display_size : display file size with total at the end (False by default)
    def display_user_files(self, user_id, file_type=None, from_date=None, to_date=None, from_post_id=None, to_post_id=None, display_size=False, reverse_order=False):
        file_list = self.__get_user_files(user_id, file_type, from_date, to_date, from_post_id, to_post_id, display_size, reverse_order)
        
        total_size = 0
        string_size = ""
        
        for file in file_list:
            if display_size:
                total_size += file["size"]
                string_size = ":" + str(file["size"])
            
            print(file["added"] + ":" + str(file["type"]) + string_size + ":" + file["post_title"] + ":" + file["full_path"])
            
        if display_size:
            print("Total size:" + str(total_size))
            
    # Download user's files.
    # Arguments :
    # - user_id : user ID
    # - file_type : File_type (all if omitted)
    # - from_date : list from this date (all posts if omitted)
    # - from_post_id : list from post ID (all posts if omitted)
    # - overwrite_file : if false, do not download if file already exists.
    def download_user_files(self, user_id, file_type=None, from_date=None, to_date=None, from_post_id=None, to_post_id=None, overwrite_file=False, reverse_order=False):
        file_list = self.__get_user_files(user_id, file_type, from_date, to_date, from_post_id, to_post_id, get_size=False, reverse_order=reverse_order)
        progress_bar = None
        current_file_size = 0
        
        print(len(file_list))
        def download_progress_hook(count, block_size, total_size):
            nonlocal current_file_size
            current_file_size = total_size
            
            data_downloaded = count * block_size
            if data_downloaded > total_size:
                data_downloaded = total_size
            
            nonlocal progress_bar
            if progress_bar.widgets[1] == "##":
                progress_bar.max_value = total_size
                progress_bar.widgets[1]= DataSize(format='%(scaled)5.1f %(prefix)s%(unit)s/' + '{:5.1f}'.format(float(total_size)/(1024.0*1024.0)) + ' MiB')
                
            progress_bar.update(data_downloaded)
        
        def download_file():
            print("Downloading " + file_name)
            
            nonlocal progress_bar
            progress_bar = ProgressBar(term_width=100, widgets=["\t", "##","|",Percentage(), Bar(), AdaptiveETA(),"|",FileTransferSpeed()])
            progress_bar.start()
            urlretrieve(file["full_path"], file_name, reporthook=download_progress_hook)
            progress_bar.finish()
        
        
        for file in file_list:
            # directory_name = file["published"] + "-" + file["post_title"]
            directory_name = user_id + "/" + file["post_title"]
            os.makedirs(directory_name, exist_ok = True)
            file_name = directory_name + "/" + file["name"]
            
            if not overwrite_file and os.path.isfile(file_name):
                print("Download skipped, file already exists :'" + file_name + "'")
                # Set file modification time to the publication date
                published = datetime.strptime(file["published"], '%Y-%m-%dT%H:%M:%S')
                os.utime(file_name, (published.timestamp(), published.timestamp()))
                os.utime(directory_name, (published.timestamp(), published.timestamp()))
            else:
                nb_download_retries = 0
                download_completed = False
                # Try to download a file three times then abort
                
                while nb_download_retries < 3 and not download_completed:
                    try:
                        if nb_download_retries != 0:
                            print('Download issue, try for the ' + str(nb_download_retries) + ' time')
                        # Initialize file modification time with current time
                        file_last_modification_time = time.time()
                        # Remove file if not first try
                        if nb_download_retries != 0:
                            try:
                                os.remove(file_name)
                            except OSError:
                                pass
                                                
                        # Launch file download
                        executor = ThreadPoolExecutor(max_workers=1)
                        download_task = executor.submit(download_file)
                        
                        nb_checks_without_file_modification = 0
                        task_successfully_completed = True
                        
                        while download_task.running():
                            # Wait 2 seconds and check if file has been modified
                            time.sleep(10)
                            
                            if os.path.exists(file_name):
                                file_current_modification_time = os.path.getctime(file_name)
                            else:
                                file_current_modification_time = file_last_modification_time
                            
                            if file_current_modification_time == file_last_modification_time:
                                nb_checks_without_file_modification += 1
                                #print('no modification : ' + str(nb_checks_without_file_modification))
                            else:
                                file_last_modification_time = file_current_modification_time
                                nb_checks_without_file_modification = 0
                                
                            # After n checks without modification, interrupt the downloading
                            if nb_checks_without_file_modification > 3:
                                task_successfully_completed = False
                                executor.shutdown(wait=False)

                        downloaded_file_size = os.path.getsize(file_name)

                        if task_successfully_completed and downloaded_file_size == current_file_size:
                            # It's OK, the file has been downloaded, stop retrying
                            download_completed = True
                        else:
                            # Try again
                            nb_download_retries += 1
                    except Exception as e:
                        print(e)
                        
                if not download_completed:
                    print('Network issues, exit !')
                    sys.exit(2)
                else:
                    # Set file modification time to the publication date
                    published = datetime.strptime(file["published"], '%Y-%m-%dT%H:%M:%S')
                    os.utime(file_name, (published.timestamp(), published.timestamp()))
                    os.utime(directory_name, (published.timestamp(), published.timestamp()))
                    
            
    # Display user collabs.
    # Arguments :
    # - user_id : user ID
    def display_user_collabs(self, user_id):
        
        # Loop all the posts
        post_list = self.__get_user_posts(user_id)
        
        collabs = []
        for post in post_list:
            post_content = post["content"]
            post_collabs = re.findall(r'@[a-zA-Z0-9_]*', post_content)
            for collab in post_collabs:
                collab = collab.lower()
                collabs.append(collab)
                
            post_collabs = re.findall(r'https://onlyfans.com/[/a-zA-Z0-9_]*', post_content)
            for collab in post_collabs:
                collab = collab.lower()
                collab = re.sub(r'https://onlyfans.com/[0-9/]*','', collab)
                collabs.append("@" + collab)
            
        for collab in sorted(set(collabs)):
            collab = collab[1:]
            # Check if collab is reachable
            if self.__check_user_exists(collab):
                result = 'https://' + self.__site + '/' + self.__service + '/user/' + collab
            else:
                result = ''
            
            print(collab + " : " + result)
             


    # Display user links found in posts.
    # Arguments :
    # - user_id : user ID
    def display_user_links(self, user_id):
        
        # Loop all the posts
        post_list = self.__get_user_posts(user_id)
        
        links = []
        for post in post_list:
            post_content = post["content"]
            post_links = re.findall(r'https://[^ <"]*', post_content)
            for link in post_links:
                links.append(link)

        for link in sorted(set(links)):
            print(link)

# Catch Ctrl-C
#def signal_handler(signum, frame):  
#    print("Program stopped")
#    sys.exit(1)
    
#signal.signal(signal.SIGINT, signal_handler)

# Command arguments : 
# - -w/--web_site : web site, required
# - -u/--user-id : user ID, required OR -f/--favorites : favorite posts
# - -s/--service : service (default onlyfans)
# - -a/--action (download-files, list-files, list-collabs
# 
#   For list and download files only
# - -ft/--file-type : file type (video, image, archive, other)
# - -fd/--from-date : parse posts added after this date
# - -td/--to-date : parse posts added before this date
# - -fpi/--from-post-id : parse posts added after this date
# - -tpi/--to-post-id : parse posts added before this date
# - -owf/--overwrite-file : overwrite existing files during download
# - -sfs/--show-file-size : show file size when executing command list-files (very slow)
# - -ro/--reverse-order : list/download from the oldest file (default is latest file)

parser = argparse.ArgumentParser(description="Tool")
parser.add_argument("-w", "--web-site", required=True, help="Web site : coomer.su or kemono.su")

source_group = parser.add_mutually_exclusive_group(required=True)
source_group.add_argument("-u", "--user-id", help="service user ID")
source_group.add_argument("-f", "--favorites", help='favorite posts', action='store_true')

parser.add_argument("-s", "--service", default="onlyfans", help="Default : onlyfans")
parser.add_argument("-a", "--action", required=True, choices=['download-files', 'list-files', 'list-collabs', 'list-links'])
parser.add_argument("-ft", "--file-type", choices=list(CKUtils.File_type), type=CKUtils.File_type)
parser.add_argument("-fd", "--from-date", type=lambda d: datetime.strptime(d, '%Y/%m/%d %H:%M:%S'), help="Date format : 'YYYY/MM/DD hh:mm:ss'")
parser.add_argument("-td", "--to-date", type=lambda d: datetime.strptime(d, '%Y/%m/%d %H:%M:%S'), help="Date format : 'YYYY/MM/DD hh:mm:ss'")
parser.add_argument("-fpi", "--from-post-id")
parser.add_argument("-tpi", "--to-post-id")
parser.add_argument("-owf", "--overwrite-file", action='store_true', help='Overwrite existing files during download')
parser.add_argument("-sfs", "--show-file-size", action='store_true', help='Show file size when executing command list-files (very slow)')
parser.add_argument("-ro", "--reverse-order", action='store_true', help='List/download from the oldest file (default is latest file)')

args = parser.parse_args()

username = ""
password= ""

if args.favorites:
    args.user_id = CKUtils.FAVORITES
    
    username = input('Enter your user name:')
    password = getpass.getpass(prompt="Enter your password:")
    
ckutils = CKUtils(args.web_site, args.service, username, password)
    
if args.action == "list-files":
    ckutils.display_user_files(user_id=args.user_id, file_type=args.file_type, from_date=args.from_date, to_date=args.to_date,
                               from_post_id=args.from_post_id, to_post_id=args.to_post_id, display_size=args.show_file_size, reverse_order=args.reverse_order)

elif args.action == "download-files":
    ckutils.download_user_files(user_id=args.user_id, file_type=args.file_type, from_date=args.from_date, to_date=args.to_date,
                                from_post_id=args.from_post_id, to_post_id=args.to_post_id, overwrite_file=args.overwrite_file, reverse_order=args.reverse_order)
    
elif args.action == "list-links":
    ckutils.display_user_links(user_id=args.user_id)
    
elif args.action == "list-collabs":
    ckutils.display_user_collabs(user_id=args.user_id)

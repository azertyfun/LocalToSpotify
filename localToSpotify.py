#!/usr/bin/env python3

import sys
import requests
import json
import base64
import os
import glob
from mutagen.id3 import ID3

TOKEN_FILE = ".localToSpotify_token"
CLIENT_ID = "" # Add yourself
CLIENT_SECRET = "" # Add yourself
CLIENT_AUTH_B64 = base64.b64encode((CLIENT_ID + ":" + CLIENT_SECRET).encode('ascii'))
REDIRECT_URI = "http://monfils.be/files/localToSpotify.php"

global global_token

def getToken():

    print("Open the following link to connect: https://accounts.spotify.com/authorize/?client_id=" + CLIENT_ID + "&response_type=code&redirect_uri=" + REDIRECT_URI + "&scope=playlist-read-private%20playlist-modify-private")
    token = input('Token? ')

    auth_data = {"grant_type": "authorization_code", "code": token, "redirect_uri": REDIRECT_URI}
    auth_headers = {"Authorization": "Basic " + CLIENT_AUTH_B64.decode('ascii')}
    print(auth_headers["Authorization"])
    response = requests.post("https://accounts.spotify.com/api/token", data=auth_data, headers=auth_headers)

    if response.status_code != 200:
        print("Error: Authentication returned status code " + str(response.status_code) + ".")
        print(response.content)
        exit() # TODO

    with open(TOKEN_FILE, "w") as f:
        f.write(response.content.decode('ascii'))

def refreshToken():
    global global_token
    refresh_data = {"grant_type": "refresh_token", "refresh_token": global_token["refresh_token"]}
    refresh_headers = {"Authorization": "Basic " + CLIENT_AUTH_B64.decode('ascii')}
    response = requests.post("https://accounts.spotify.com/api/token", data=refresh_data, headers=refresh_headers)

    if response.status_code != 200:
        print("Error: Authentication returned status code " + str(response.status_code) + ".")
        print(response.content)
        exit() # TODO

    global_token = json.loads(response.content)

    with open(TOKEN_FILE, "w") as f:
        f.write(json.dumps(global_token))

def get(url):
    get_headers = {"Authorization": "Bearer " + global_token["access_token"]}
    response = requests.get(url, headers=get_headers)
    if response.status_code == 401:
        print("Authentication expired, refreshing token...")
        refreshToken()
        response = requests.get(url, headers=get_headers)

    return response

def post(url, post_data):
    post_headers = {"Authorization": "Bearer " + global_token["access_token"], "Content-Type": "application/json"}
    response = requests.post(url, headers=post_headers, data=post_data)
    if response.status_code == 401:
        print("Authentication expired, refreshing token...")
        refreshToken()
        response = requests.get(url, headers=post_headers, data=post_data)

    return response

def createPlaylist(me, name):
    data = {
        "name": name,
        "public": False,
        "description": "Created by Local To Spotify"
    }
    response = post("https://api.spotify.com/v1/users/" + me["id"] + "/playlists", json.dumps(data))
    if response.status_code != 201:
        print("Could not create playlist '" + sys.argv[1] + "'. Status code: " + response.status_code + ".")
        print(response.content)
        exit(1)

    playlist = json.loads(response.content)
    return playlist

def getMe():
    response = get("https://api.spotify.com/v1/me")
    if response.status_code != 200:
        print("Could not get user information: status code is " + str(response.status_code) + ".")
        print(response.content)
        exit(1)

    return json.loads(response.content)

def addToPlaylist(me, playlist, uris):
    uriChunks = [ uris[i:i+100] for i in range(0, len(uris), 100) ]

    for uriChunk in uriChunks:
        data = {
            "uris": uriChunk
        }
        print("Adding " + str(len(uriChunk)) + " songs to the playlist.")
        response = post("https://api.spotify.com/v1/users/" + me["id"] + "/playlists/" + playlist["id"] + "/tracks", json.dumps(data))

        if response.status_code != 201:
            print("Error: could not add songs to playlist. Status code: " + str(response.status_code))
            print(response.content)

def getMusicFilesInDirectory(dirName):
    print("Looking for files in '" + dirName + "'.")

    files = []
    for filename in glob.iglob(dirName + "/**", recursive=True):
        if os.path.isfile(filename):
            files.append(filename)

    return files

def getArtists(songInfo):
    artists = []
    for artist in songInfo["artists"]:
        artists.append(artist["name"])

    return artists

def sameSong(songInfo, title, artist, acceptRemasters, acceptArticleChanges):
    if songInfo["name"].lower() != title.lower():
        remastered = acceptRemasters and "remaster" in songInfo["name"].lower()
        articleChange = acceptArticleChanges and songInfo["name"].lower()[4:] == title.lower()
        if acceptArticleChanges and articleChange or acceptRemasters and remastered:
            return True

        return False

    for a in songInfo["artists"]:
        articleChange = acceptArticleChanges and a["name"].lower()[4:] == artist.lower()
        if a["name"].lower() == artist.lower() or articleChange:
            return True

    return False


# Check argv
if len(sys.argv) < 3 or len(sys.argv) > 6:
    print("Usage: python3 localToSpotify.py <Playlist name> <Directory> [-v] [--accept-remasters] [--accept-small-changes]")
    exit(1)

verbose = False
if "-v" in sys.argv:
    verbose = True

acceptRemasters = False
if "--accept-remasters" in sys.argv:
    acceptRemasters = True

acceptArticleChanges = False
if "--accept-article-changes" in sys.argv:
    acceptArticleChanges = True

if verbose:
    print("Accept remasters: " + str(acceptRemasters))
    print("Accept article changes: " + str(acceptArticleChanges))

# Check the directory we want to scan exists
if not os.path.isdir(sys.argv[2]):
    print("Error: '" + sys.argv[2] + "' is not a directory.")
    exit(1)

# Create the auth token if necessary
if not os.path.isfile(TOKEN_FILE):
    getToken()

with open(TOKEN_FILE) as f:
    global_token = json.load(f);

    # Get user ID and create playlist
    me = getMe()
    playlist = createPlaylist(me, sys.argv[1])


    files = getMusicFilesInDirectory(sys.argv[2])

    addedFiles = []
    noMetadataFiles = []
    notAddedFiles = []

    uris = []

    for f in files:

        try:
            metadata = ID3(f)
        except: # The file may very well not be a valid music file; just skip to the next one.
            if verbose:
                print("could not load metadata for '" + f + "'.")
            noMetadataFiles.append(f)
            continue

        if metadata != None:
            if not 'TIT2' in metadata or not 'TPE1' in metadata:
                if verbose:
                    print("Could not get metadata for '" + f + "'.")
                noMetadataFiles.append(f)
                continue

            title = metadata['TIT2'].text[0]
            artist = metadata['TPE1'].text[0]

            if verbose:
                print("Looking for " + title + " by " + artist + "...")

            url = "https://api.spotify.com/v1/search"
            params = {"q": "track:" + title + " artist:" + artist, "type": "track", "limit": 8}
            response = requests.get(url, params=params)
            if response.status_code != 200:
                print("Error: spotify search returned status code " + str(response.status_code) + ".")
                notAddedFiles.append(f)
                continue

            song = json.loads(response.content)

            if len(song["tracks"]["items"]) == 0:
                if verbose:
                    print("Error: could not find results for " + title + " by " + artist + ".")
                notAddedFiles.append(f)
            else:
                songInfo = song["tracks"]["items"][0]
                if sameSong(songInfo, title, artist, acceptRemasters, acceptArticleChanges):
                    if verbose:
                        print("Found.")
                    uris.append(songInfo["uri"])
                    addedFiles.append(f)
                else:
                    print("Error: Found " + songInfo["name"] + " by " + ", ".join(getArtists(songInfo)) + " instead of " + title + " by " + artist + ".")

                    print("Closest matches:")
                    print("1) Don't add anything")
                    for i in range(0, len(song["tracks"]["items"])):
                        songInfo = song["tracks"]["items"][i]
                        print(str(i + 2) + ") " + songInfo["name"] + " by " + ", ".join(getArtists(songInfo)))

                    answer = input("Song to add? [2] ")

                    if answer == "":
                        answer = "2"

                    if answer.isdigit() and int(answer) - 2 < len(song["tracks"]["items"]) and int(answer) != 1:
                        i = int(answer) - 2
                        uris.append(song["tracks"]["items"][i]["uri"])
                        addedFiles.append(f)
                    else:
                        notAddedFiles.append(f)
        else:
            if verbose:
                print("could not load metadata for '" + f + "'.")
            noMetadataFiles.append(f)
            continue

    addToPlaylist(me, playlist, uris)

    print("Done.\n")

    print("ADDED FILES\n-----------")
    for f in addedFiles:
        print(f)

    print("\nFILES NOT ADDED\n---------------")
    for f in notAddedFiles:
        print(f)

    print("\nFILES WITH NO METADATA\n----------------------")
    for f in noMetadataFiles:
        print(f)


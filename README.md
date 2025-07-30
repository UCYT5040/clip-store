# Clip Store

## Purpose

Clip Store allows you to store video clips for longer than the 3 hours that Google Home normally keeps them.

## Features

- Download & view clips from Google Home
- Batch delete old clips
- Mark clips as immune to batch deletion

## Setup

Get a Google token:

```shell
docker run --rm -it breph/ha-google-home_get-token
```

Set variables in `.env` (or manually):

```dotenv
GOOGLE_TOKEN=your_token_here
GOOGLE_EMAIL=your_email_here
USERS=name1;password1,name2;password2
```

Run with UV:

```shell
uv run --module flask run
```

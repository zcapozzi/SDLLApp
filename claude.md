

# PROJECT BOOT SEQUENCE

When starting work in this repo:

1. Read this file fully first.
2. Then list the directory tree (depth 2–3 max).
3. Identify all top-level folders and all `.md` files.
4. Read ONLY the following files next:
   - *.md
5. Build a mental map of:
   - purpose of each folder
   - key abstractions
   - data flow / system flow
6. Before editing anything, summarize understanding back to user.

# Purpose

This project is to build a web-application that I can deploy to manage our Little League.

# High-Level Criteria

I want to use Green/Red TDD for this project; our color palette is orange and forest green; i would like a python script that I can run to verify that the project is working as expected and that all tasks are being executed successfully. 

# Eventual deployment

This is going to be a public facing website (southdurhamlittleleague.org) that league admins will be able to log in to. Plan for it to be deployed (possibly via Vercel); I'm agnostic about hosting, but I would like the hosting costs to be under $300 per year.

# LocalHost

This should be deployed to port 8084 locally

# Database

I have dumped the current database that I'm using in a command-line project to Dump20260702.sql; if it makes sense, it would be good to be able to spin up a local DB for testing that incorporates this information and linkages.

# Sending Updates to admins

Review `sendMessage.md` for instructions on keeping admins up to date on progress or otherwise sending out emails and text messages
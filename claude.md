

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

# Development Guidelines

## Scroll-Back After Form Submissions

When a page has forms that submit and redirect back to the same page (common pattern for inline editing), the page MUST scroll back to where the user made the edit. This provides better UX by not forcing users to scroll back down after every edit.

### Implementation Pattern

1. **Route**: Track which element was edited and append an anchor to the redirect URL
   ```python
   if request.method == 'POST':
       action = request.form.get('action')
       anchor = None  # Track which element to scroll to

       if action == 'update_item':
           item_id = int(request.form.get('item_id'))
           # ... do the update ...
           anchor = f'item-{item_id}'

       redirect_url = url_for('blueprint.route_name')
       if anchor:
           redirect_url += f'#{anchor}'
       return redirect(redirect_url)
   ```

2. **Template**: Add IDs to the elements that can be edited
   ```html
   {% for item in items %}
   <tr id="item-{{ item.id }}">
       <!-- form fields here -->
   </tr>
   {% endfor %}
   ```

### Pages with Scroll-Back Implemented
- Field Properties (`/fields/properties`) - `#field-{id}`
- Field Time Restrictions (`/fields/time-restrictions`) - `#field-{id}`
- Field Allocations (`/fields/allocations/<year>/<is_spring>/manage`) - `#field-{id}`
- Fields Index (`/fields/`) - `#field-{id}`
- Schedule Settings (`/seasons/<year>/<is_spring>/schedule-settings`) - `#league-{id}`
- Manage Leagues (`/seasons/<year>/<is_spring>/leagues`) - `#league-{id}`
- Manage Teams (`/seasons/<year>/<is_spring>/teams`) - `#league-{name}`
- Manage Playoffs (`/seasons/<year>/<is_spring>/playoffs/<league>`) - `#placeholder-{id}`, `#seeds-section`, `#brackets-section`

### When Adding New Forms
Any new page with inline editing that redirects to itself MUST implement scroll-back following this pattern.
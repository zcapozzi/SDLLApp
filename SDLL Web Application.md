## SDLL Web Application

Our little league uses Google Sheets to manage games and locations. This is fine to start, but once the year starts and changes have to be made (i.e. rainouts), the system becomes very unwieldy. This is for two reasons. First, a change made to the Google Sheet does not easily turn into a notification for all the other stakeholders that need to know about the game change (umpires, coaches, parents). Second (and maybe related), a change to a Google Sheet does not have the capacity for any additional logic (i.e. you have two games scheduled at the same time at the same field).

I would like to build a web-application that can be accessed by the various stakeholders to better manage the process of in-season game changes. In particular, when a change needs to be  made, the site needs to:

1. Allow an approved scheduler to see options for a re-schedule  
2. Trigger a series of alerts and other actions to notify other stakeholders of the change

We are currently using Assignr for the umpire communication and assignment part of this; they have an API, so I think it’s reasonable to plan on using this system to keep Assignr up to date. Long-term, this may be able to replace Assignr.

## Stakeholders

There are several core stakeholders from the SDLL Board of Directors who would actually use the system. There are a bunch of other stakeholders who would get notified as a downstream result of a change made in the site or who may have read-access to the site.

**Scheduler** \- This is the person who is responsible for actually making changes to the schedule; 

**Umpire Coordinator** \- The Scheduler is the person responsible for deciding what changes will be made; the Umpire Coordinator is responsible for making sure that the umpires know about the changes

**Coaching Coordinator** \- Similar to the Umpire Coordinator, the Coaching coordinator needs to make sure that the coaches are notified of the change so that they can notify their teams

**Other SDLL Board Member** \- Down the road, I could imagine other SDLL board members having read access to the site, but this is not important to start

**Coaches** \- Coaches probably wouldn’t have access to the site, at least if it’s just being used for scheduling changes, but they absolutely need to know when a change is made

**Umpires** \- Similar to the coaches, they need to be notified when a change is made

**Umpire Organizations** \- We manage a pool of umpires (i.e. we know who is going to which game), but we also contract with other organizations that provide umpires (i.e. we do not know which specific umpire they are sending); we may eventually give them a log in to see which games they have coming up

## Data Model & Initial Set up

I think we will probably still use the Google Sheet to create the initial schedule; eventually, I think it would make more sense to use the web application, but for now, assume that the schedule is going to be created outside of the application and loaded in at the start of the season. Once that is done, the system would be used for changes and those changes would need to be written to the spreadsheet (either automatically or by the Scheduler manually).

We will use a MySQL database to store the various data objects, which would include:

* SDLL\_Team\_Seasons \- a record for each team (teams are not persistent from year to year); we have a fall and spring season, so it’s not just a year differentiator  
  * There will be placeholder team records for TBD games (i.e. Seed 1 or winner of a previous game); the scheduler may need to set up the teams with one of the placeholders and then replace the placeholder team later  
* SDLL\_Umpires \- each individual umpire who is potentially going to umpire one of our games  
* SDLL\_Umpire\_Games \- a combination of umpire and game; there could be multiple umipres for a single game; umpire assignments could be created, then cancelled if the umpire can’t do the game  
* SDLL\_Games \- a single game record between two teams (i.e. two separate SDLL\_Team\_Seasons  records); games include a start\_date, duration, field/location, home\_ID and away\_ID  
  * Note that the home\_ID and away\_ID are irrelevant from an umpire scheduling perspective; a game may be a placeholder with teams to be added later; the umpire assignment does not need to know the teams, just the league/location/date/time  
  * As a result, the home and away\_IDs are optional when the game is created; they can be added back later; the game records align more closely with field permits than with a combination of teams  
* SDLL\_Locations \- a combination of location (i.e. address/name) and field; a single location could have multiple fields  
* SDLL\_Users \- a user of the web application  
* SDLL\_Coaches \- a person who is a coach in SDLL  
* SDLL\_Coach\_Seasons \- we should have a separate record tying an SDLL\_Coach (a person) to an SDLL team season (they coached this team in this season)  
* SDLL\_Organization \- a little league that is using this application

## Scheduling Workflow

There are four stages to scheduling

1. Teams \- Prior to the draft, we identify the number of teams based on the number of registered players. Those teams have head coaches and contact information, but no names. We just name them based on the league and a number (i.e. BB \- A Team 1\)  
   1. We play inter-league games, so the system needs to support the creation of teams from other leagues who will only play sporadic games  
2. Fields \- Around the same time, we get our field allocations from Durham Parks and Rec. We combined that with our other fields and we set the times that we have the permits. This will inform what fields are available to which leagues at which times. Think of it like a fixed number of game slots. We may not use every one, but it’s the ceiling  
3. Games \- We specify a number of games per team per league and whether or not we are going to have a playoffs or not. We will need to specify the format of the playoffs to determine the number of games. Games include scrimmages, games, and end-of-season tournaments. Not all games will require an umpire. When we are making the initial schedule, we try to balance start times by team so that no one team has more late starts than another (or as close as possible)  
   1. We have a fixed number of slots that we have been allocated by the people who own the field assignments. Every slot may or may not have a game in it. Some slots may include two games if we have access to the field from 5-10 pm. We can’t have overlapping games in a single slot  
   2. We have a fixed number of potential games for each division, not all will actually end up being played  
4. Throughout the season, reschedules happen due to rain and other stuff. When that happens, the game record remains, but we need to change the date/time/location. So that means a game must have one of several statuses: scheduled, completed, postponed, cancelled. Postponed means that we are planning to play the game, but we don’t know when. Cancelled means we are not going to play the game at all

## Implicit Knowledge: Scheduler

*This section contains the tribal or implicit knowledge that the scheduler has developed from the day-to-day management of their role.*

### Game Durations

Games can have different set durations (playoff games are going to be longer because they do not have time limits in some divisions). The league specifies ahead of time whether games are no time-limit or a specific time limit; it’s ok if a game goes long, but it’s not OK to schedule two playoff games in a 5:30 and 7:30 slot if the 5:30 game has no time limit.

### Field Priority Notes

AA/AAA/Majors play all games at Herndon. Each division plays 2 days a week. AA always on Saturday. Others can change.  
Intermediate can only play at Cedar Falls 1, Hillside, Parkwood, Pineywood, and Cresset.  
Juniors can only play at Githens Baseball and Lowe’s Grove Baseball  
All other divisions can pay anywhere/anytime but there are preferred fields.  
Practice only at Shepard if possible.   
Cresset can easily hold 2 teams for a practice.  
Parkwood can easily hold 2 teams for a practice at 5:30, but not at 7:30.  
Githens softball can hold 2 teams for a practice.  
Southern Boundaries 1 is a practice only field for everyone due to base path distances.  
Any kid pitch team CAN practice at Lowe’s Grove baseball or Githens baseball, but they don’t prefer it.  
Softball Majors prefers to play at Parkwood but we share the space among any division that doesn’t use Herndon.  
Baseball tee ball only plays as Pearsontown.

**Top Fields:**  
Parkwood	  
Pineywood  
Herndon  
Southern Boundaries	  
Hillside  
**Mid Range Fields:**  
Githens Softball  
Alston Ridge  
Ephesus  
Cedar Falls

**Least Preferred Fields:**  
Cresset  
Lowe’s Grove Softball  
Shepard  
						  
Times:  
AA,AAA, Majors, Intermediate, SB Minor, SB Major: 5:30 OR 7:30  
Tee, Rookie SB, Rookie BB, A: 5:30 only  
Juniors: 5:30 b/c their fields don’t have lights					

### Setting up a new Season

When I go to start the Fall Season, how much should I be using the Spring season as a template? Are field allocations generally the same? Are the number of teams in each division generally the same? Are the days of the week that each league plays on generally the same?

## Implicit Knowledge: Umpire Coordinator

*This section contains the tribal or implicit knowledge that the umpire coordinator has developed from the day-to-day management of their role.*

If we are past the start of the game, we should be calling Marti (Diamond) or Vance (Dynamic) if their umpire has not arrived; they’ll need to know which field at which location we are talking about because that’s how they look it up in their system.

Umpires don’t really care which teams are playing as long as they know the division. It’s helpful to communicate the teams and the coach names to the umpire, but if the teams change for their game, that doesn’t require an update notification.

## Notification System

We don’t send a ton of emails, so we use our google email with SMTP and we shouldn’t ever hit our daily sending limit. This is primarily for communicating with our umpire partner organizations. For our own umpires that we manage, we use Assignr, and they have an API that can send messages.

We should be able to plug in a Twilio (or an alternative) API key and send text messages as needed. This is better for a last minute message to coaches about an umpire situation or to ask about some sort of scheduling question.

Long-term, we should enable AWS for emails since this could eventually be used to email parents and individual players.

## Technical Constraints

I am comfortable with Flask/Python/GAE, but any framework that you think will combine ease of deployment with limited cost is fine. Users must log-in and be authenticated; be sure to use state of the art open-source encryption so that names, phone numbers, etc are encrypted at rest; we will need to store user credentials in the system rather than try to have any integration with SSO.

I have a set of CSS files that I’d like you to use to keep the design system consistent with other projects.

There should be a configurable logging system where, for each type of action that a user is coming to the site to accomplish, I can set, via a JSON file, whether I want logging OFF, ON, or EXTREME. ON means that the request and whether it was fulfilled should be logged with timestamps. EXTREME means that every step of the process should be logged with appropriate context. 

This must be a mobile-friendly web application. It's fine (even desirable) if there are features that are more usable on a laptop, but the ability to lookup a game, make changes,  and trigger notifications must be easily done on a phone.

The league's colors are green and orange, but don't go overboard. I'm going for a clean, modern feel, but for places where a touch of color would help, a green and orange palette would be good

Admins will create new user accounts. No password requirements other than 8 characters. Password reset can be simply email-based reset links.

Sessions can log out after 3 months; multi-device login is allowed; yes, it should remember the user

No two-factor auth is needed; yes, please rate-limit logins; no email verification for new accounts since admins are going to create them. User information for users of the application include just name, phone, email, orgID (for now, this is only being used by SDLL, but I see no reason not to design it to be used by other organizations; it’s not important to store data across organizations separately, but users from different organizations should have no knowledge of each other)

For development versus production, I’ll be using localhost. This is what I’m using right now; I’m not wedded to GCP though:

@echo off  
:loop  
cd C:\\Users\\zcapo\\Documents\\workspace\\LacrosseReference\\LRP\\LRP\_flask  
set FLASK\_APP=main  
set FLASK\_ENV=development  
set FLASK\_DEBUG=1  
CALL flask run \-h localhost \-p 8080  
goto loop

I’ll have a domain once we prove out that this works. But for now, just do it in localhost and once it’s working, we can handle the domain. It will need SSL/HTTPS support. There are no compliance requirements, but I would like for names to be stored encrypted at rest.

AWS for email; Twillio for text; Telegram for admin messaging; there should be a client\_secrets.json file that contains a local and web copy of the key config variables and API keys; the app should look up the correct one based on whether it's on local versus prod

Whatever logging is fine; error notifications for admins would be good; don’t worry about uptime monitoring

As mentioned, use a MySQL database; keep historical records forever; no backup requirements, but it should be backed up

We have a service account email for interacting with Google Sheets and Google Docs

Assume the smallest instance size for now. I'm more worried about hosting costs than performance since there will only be a handful of potential users at the start

## MVP vs. Future Features

The MVP (minimum viable product) should be very basic; it should allow authenticated users to login and make changes to existing games or add new games; it should create a list of required actions to communicate those changes to the appropriate stakeholders; it should allow those users to execute the appropriate notifications (either email or text) via an interface that triggers emails or texts. It should make it easy to see the overall picture of the season’s games and it should also provide some view of what’s coming up (do we have umpires for all upcoming games?) It should also support creating a new season by copying in a prior season’s configuration.

Longer term, I think it would make sense to make this the OS for our league. That would include the basic management of scheduling as well as things like:

* CRM for league sponsorships  
* Ticket Management for field maintenance  
* Registering umpires, handling training, assigning umpires to games and handling communications  
* Marketing for social media and a CMS to handle marketing materials  
* Automatically create a schedule based on a list of teams, field availability and other considerations  
* Have parents and players register and pay through our own site
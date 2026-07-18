Hi all,

Janna and I have been talking about the need to systematize the scheduling / umpire coordination tasks. I can only speak for myself, but the odds that I could transition the systems and processes I've built to my successor at the end of my term are very low.

I have spoken to Justin about investing $600 to explore building a system to codify our processes. He said that was doable from a budget perspective, and so this email is to document our goals.

The immediate objective is to see how feasible it is to build a web application that can do three things:

1. Allow the scheduler to input field allocations, teams, and league-specific nights of the week and generate a potential schedule automatically  
2. Automatically populate a Read-Only Google sheet style list of umpire slots for our partners  
3. Allow the scheduler to reschedule or move games to different locations / times AND automatically generate the communications to notify umpires

I’ve built systems like this in the past. The new AI tools make it feasible to build custom systems like this quickly and iteratively. And much of the technical infrastructure already exists because of the work I’ve done automating pieces of the Umpire Coordinator role. I think a $600 investment should be enough to build a system that we can test out in the fall season. (For extra context, see the end of this email.)

So that’s the proposal. Long-term, a system like this could even evolve to codify more and more of our leagues operations (fundraising and evaluations are the two that come to mind first and foremost). That said, I’m intentionally keeping this experiment narrow in scope; if we can prove out the concept with Scheduling / Umpire Coordination, we could certainly expand it to more places.

Let me know if there are any glaring objections to what we are proposing.

Zack

P.S. (Extra context)

Essentially, scheduling and umpire coordination have two phases: initial build and dealing with disruption.(Apologies for the long email; I’m partially using this to organize my own thoughts.)

**Initial Build**

Janna gets team counts, schedule assignments and field allocations and then designs a schedule that gets every team in the right place on the right day. I get those game dates and send them out to our umpire groups to make sure all the games are filled. 

This process is repeated in miniature throughout the season as 147 games and eventually playoff games are scheduled. 

Our goal, from a system perspective, is to make the schedule design process more automated. Instead of Janna having to take her teams/field allocations and manually build a schedule, the system will automatically do this. The system will also try to ensure balance in terms of fields / umpire groups / time slots for each team.

**Dealing with Disruption**

The other part of our job is dealing with issues as they come up. Lights stop working. We got rained out. An umpire cancelled at the last minute. These things happen every season and our job is to make sure that all games are played and that each one has an umpire. Where the Initial Build phase is tedious, this phase is more about coordination under pressure. At least from my perspective, it’s where the relationships with Vance/Marti are most valuable. It’s also an area that would be much less challenging to handle with a more automated system.

In our current set up, it’s very difficult to know when a change is made and what downstream actions need to be taken. I have built automated systems that, for example, notify an umpire when a game has changed locations, but they are brittle and typically still require a lot of manual checking and verification. 

Some things are less about the coordination element and more about automating the communication. If an umpire can’t do a game, you have to pull information from several different places to try and figure out what our options are for finding a replacement. Then sending out those communications is another manual process.

Our goal, from a system perspective, is to have actions always produce a set of follow up actions. If a game is rescheduled, that should trigger follow-ups around informing the coaches and informing the umpires. And when possible, those actions should be able to be triggered from within the system rather than having to manually go all over the place to make them happen.


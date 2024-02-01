# Royals-V2

## TODO
  - [x] controller revamp for better focus-lock handling
  - [x] Delays - test actuals with Spy++ and adjust. If longer, it could be due to SendInput exec time, so test this
  - [x] royals.actions to revisit - jump_on_rope, teleport/telecast
  - [ ] Improve relevance of logs
  - [ ] Task cancellation - Refactor how callbacks are triggered, such that if necessary, a callback coroutine is used to await for some time before updating data
  - [x] Task Cancellation for movements - make "controller.move" cancellable, but other functions (tp, telecast, jump rope, etc.) non-cancellable.

### Inventory Cleanup
- [ ] Ability to add custom connections (mystic door) from/to current minimap and nearest town
- [ ] Basic (incomplete) coding of relevant nearest towns - just enough to get to npc
- [ ] NPC selling mechanics
- [ ] CompoundAction implementation
- [ ] Inventory parsing for godlies?
- [ ] Storage mechanics

### Controller-revamp
- [ ] Cleanup the creation of inputs and enable better control of the focus lock on complex actions
  - Ex: can call controller.move with a list of directions+durations, and it will only acquire/release once.

### Leeching Engine
  - [x] Rebuffing from Leechers
  - [ ] Ultimate Cast failsafe - check if MP has changed by at least X%
  - [x] Enhanced telecasting
  - [ ] Multi-client blockers/parsers
  
### Generators
  - [ ] MobCheck : 2nd reaction - add full sentences (more elaborate choices)
  - [ ] MobCheck : Unblock on 2nd reaction IF mobs are detected again
  - [ ] Check character still alive
  - [ ] Check Potions, Pet Food, Mount Food, Magic Rocks left
  - [x] Cooldown buffs
  - [ ] Inventory Management
    - [x] Basic parser to check space left
    - [ ] Basic actions to clear inventory at town
    - [ ] Advanced parser to check stats on each item
    - [ ] Advanced actions to store godlies
  - [x] Automated AP distribution
  - [x] Generic Generator class for botting library
  - [ ] Add failsafe on MobHitting (how??)
  - [x] Add failsafe on Rebuff (look for fresh buff icon in top right screen)
  - [ ] Add failsafe on any Rotation Generators - Movement is expected if action is not cancelled
  - [x] Streamline reactions for AntiDetection generators

### Anti Detection Features
  - [ ] Chat Parsing (try grayscale preprocessing on "general" lines) + GPT Automated Responses
    - Idea: When detecting relevant lines, minimize chat and scroll up, then read that line without background noise!!!
  - [ ] GM Logo detection
  - [ ] Abnormal Status Detection (look for gray line types)
    - [ ] Stunned
    - [ ] Seduced
    - [ ] Cursed (reverse directions)
  - [x] Minimap Parsing to ensure still in proper map + random reaction
  - [ ] Minimap Parsing for strangers + random reaction
  - [ ] Minimap Parsing for unexpected self movements (stray too far from target?) + random reaction
  - [ ] Blue Notification detection (chat invite, other invites, etc)
  - [x] Mob freeze (from a GM) + random reaction
  - [ ] Inventory (mesos) parsing to ensure loot is still dropping from mobs + random reaction
  - [ ] For complex movements (teleport, telecast, cast skill with attacking skills, etc), use Spy++ to find exact key combinations when done by human, and make sure to properly replicate (should be very easy)
  - [ ] Nice-to-have, for Ulu only - look into building an "unknown" object detection method, using UNKAD methodology or anomaly detection

### Discord
   - [ ] Add a callback on user-messages to confirm action (such as writing to chat) properly made
   - [ ] Implement multi-bot parser

### Character detection
  - [ ] Standardize code and transfer detection framework into botting library
  
### QueueAction
  - [ ] Implement better handling of QueueAction Priority
  - [ ] Add action attributes to enable IPC
  
### Mob detection
  - [ ] Clean the pre-processing to remove the additional layer of the filter function
  - [ ] Define additional generic detection functions for mobs
  - [ ] Combine with HP bar
  
### RoyalsData Management
  - [ ] Add a Loop ID on every iteration. When data is updated, assign it a loop id. only update when loop id is different.
  - [x] Split into several subclasses, each specific to a generator
  - [ ] Re-split data further into interface/mechanics components instead of generator types (ex: MinimapData, PathingData, MobData, etc)
  - [ ] Add a PerformanceData class for monitoring (mesos/h, exp/h, etc)
  - [x] DecisionEngine should not have to update anything. Each Generator should deal with their own requirements.

### Error Management
  - [ ] Deal with KeyboardInterrupt to ensure all keys are released from all clients
  - [ ] Ability to close all clients if error occurs
  - [ ] Ability to send all characters to lounge if error occurs

### Misc
  - [ ] Ability to combine multiple Engines into a single process (ex: all buff mules together, or mages in same ch together)
  - [ ] Add Macros + cast_macros which is cancellable in between each cast
  - [ ] streamline keybindings configs
  - [ ] Add variable speed/jump management
  - [x] Add slice creation from box objects used to crop a numpy array (considers the client margins as well)
  - [ ] Skill Specs Finder
  - [x] Mouse movements and mouse clicks
  - [ ] Finalize Discord communications - Control of which process are to respond to user commands
  - [ ] UnitTests on the botting library

### Documentation
  - [ ] Botting.core
    - [x] .bot
    - [ ] .communications
    - [x] .controls
  - [ ] Royals (entire package)

### Game Interface
  - [ ] Quickslots
  - [ ] Inventory
  - [x] Level up detection
  - [ ] HP bar detection (check if still alive)

## Nice to have
  - [ ] Chat - Try additional pre-processing: Thresholding (improved?), Denoising (application of Gaussian and/or Median Blur), Contrast Enhancement (Make text more distinguishable from background)
  - [ ] Chat - Pre-trained model for semantic segmentation? Could help distinguish text from the rest.
  - [ ] Chat - Other OCR libraries? OCRopus & EasyOCR in particular.
  - [ ] Chat - Otherwise, build a modelling dataset with tons of chat lines and train a model to read text.
  - [ ] Bossing idea - use "Action Recognition" algorithms to detect boss attacks and react accordingly - Ask GPT about it
![image](https://github.com/FlawlessNa/Royals-V2/assets/106719178/c2620077-d36e-4a8d-b39b-f200a196cd2e)

# Royals-V2

## Bug Fixes (Current Branch)
- [ ] Minimap handling between CheckStillInMap and InventoryManager
- [ ] Cancellation of NPC Selling seems to be problematic because it has a return value
- [ ] Party Re-buff is broken (casts way too much), for casting non-attack skill (since there's a rebuff validation), can simply cast once.
  - Split into individual buffs and only re-cast buffs that didn't go through
- [ ] Fix algo for returning from shop - add prints of horizontal distances and such.

## Performance Branch
- [ ] Major Refactoring of Generators - needs to be easier to implement.
  - Idea: For more complex (multi-step) Generators, launch an infinite "idle" task that blocks other tasks from scheduling except those from same generator. Cancel that idle task when generator is done.
- [ ] Ability to use Multiple clients within a single Engine
  - Create a new layer "Client" within each Engine -> Each client has its own data and generators
  - Engine now groups those "Client" and runs then asynchronously.
  - Need to have multiple instances of EngineData for 1 engine (1 instance per client)
  - Blockers/Unblockers need to work for each client individually
- [ ] Ability to only retrieve first action in pathfinding parser instead of entire actions
- [ ] Look into leveraging psutil for performance monitoring of CPU resources by client/process
  - Also look into managing the Manager Process since it is a new feature that needs to spawn a process
- [ ] Look into using Profilers (cProfile, line_profiler) to identify bottlenecks in the code
- [ ] Look into "blocked" generators could wait on a mp.Event/Condition semaphore to reduce CPU consumption
- [ ] Convert generators into asynchronous generators? Each becomes an infinite "task" (in child process) that run concurrently
  - With this framework, perhaps each generator can await on a QueueAction it submits and this "blocks" itself for the duration
- [ ] Look into using asyncio DEBUG mode (PYTHONASYNCIODEBUG=1) to identify potential issues with the code
- [ ] Look into leveraging loop.run_in_executor(concurrent.futures.ProcessPoolExecutor) for CPU-intensive operations?
- [ ] Check if tasks created with executor.create_task should also be awaited? If not, the enclosing task may cancel if it terminates before

## Leeching Branch - TODOs
- [ ] Multi-client blockers
- [ ] Multi-client parsers
  - [x] controller revamp for better focus-lock handling
    - [ ] Release keys on cancellations only when necessary?
    - [ ] Rotations - More fluidity? -- Idea: using squeezed_movements, translate into callable functions, but those are only keydowns with no duration and/or keyups. keyups are triggered when movement changes or when focus changes.
    - [ ] Automated Repeat Feature on anything - not just move (aka Ultimate casting during animation time, etc)
  - [ ] Improve data management - especially when minimap is being toggled.c
  - [ ] Task cancellation - Refactor how callbacks are triggered, such that if necessary, a callback coroutine is used to await for some time before updating data
  - [x] Task cancellation for movements - make "controller.move" cancellable, but other functions (tp, telecast, jump rope, etc.) non-cancellable.
    - A big advantage is that blocking generators will automatically block generators from other characters on the same engine
  - [ ] Ability to "reset" generator data? - goes with better data management

### Inventory Cleanup
- [ ] Big code clean-up required.
- [x] Ability to add custom connections (mystic door) from/to current minimap and nearest town
- [ ] Basic (incomplete) coding of relevant nearest towns - just enough to get to npc
- [x] NPC selling mechanics
- [x] CompoundAction implementation
- [ ] Inventory parsing for godlies?
- [ ] Storage mechanics

### Generators
  - [ ] MobCheck : 2nd reaction - add full sentences (more elaborate choices)
  - [ ] MobCheck : Unblock on 2nd reaction IF mobs are detected again
  - [ ] Check character still alive
  - [ ] Check Potions, Pet Food (_failsafe to PetFood), Mount Food, Magic Rocks left
  - [ ] Inventory Management
    - [ ] Advanced parser to check stats on each item
    - [ ] Advanced actions to store godlies
    - [ ] Refactor the NPC Shop UI into its own Visual class
    - [ ] Refactor InventoryActions into royals.actions functions
    - [ ] Clean the remainder of InventoryChecks and InventoryManager
  - [ ] Add failsafe on MobHitting (how??)
  - [ ] Add failsafe on any Rotation Generators - Movement is expected if action is not cancelled

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
  
### Mob detection
  - [ ] Clean the pre-processing to remove the additional layer of the filter function
  - [ ] Define additional generic detection functions for mobs
  - [ ] Combine with HP bar
  
### RoyalsData Management
- [ ] Re-split data further into interface/mechanics components instead of generator types (ex: MinimapData, PathingData, MobData, etc)
- [ ] Add a PerformanceData class for monitoring (mesos/h, exp/h, etc)
- [x] DecisionEngine should not have to update anything. Each Generator should deal with their own requirements.

### Error Management
  - [x] Deal with KeyboardInterrupt to ensure all keys are released from all clients
  - [ ] Ability to close all clients if error occurs
  - [ ] Ability to send all characters to lounge if error occurs

### Misc
  - [ ] Ability to combine multiple Engines into a single process (ex: all buff mules together, or mages in same ch together)
  - [ ] Add Macros + cast_macros which is cancellable in between each cast
  - [ ] streamline keybindings configs
  - [ ] Add variable speed/jump management
  - [ ] Skill Specs Finder
  - [ ] Finalize Discord communications - Control of which process are to respond to user commands
  - [ ] UnitTests on the botting library

### Documentation
- [ ] Botting.core
  - [x] .bot
  - [ ] .communications
  - [x] .controls
- [ ] Royals (entire package)
- [ ] Improve relevance of logs

### Game Interface
  - [ ] Quickslots
  - [x] Inventory
  - [x] Level up detection
  - [ ] HP bar detection (check if still alive)

## Nice to have
  - [ ] Chat - Try additional pre-processing: Thresholding (improved?), Denoising (application of Gaussian and/or Median Blur), Contrast Enhancement (Make text more distinguishable from background)
  - [ ] Chat - Pre-trained model for semantic segmentation? Could help distinguish text from the rest.
  - [ ] Chat - Other OCR libraries? OCRopus & EasyOCR in particular.
  - [ ] Chat - Otherwise, build a modelling dataset with tons of chat lines and train a model to read text.
  - [ ] Bossing idea - use "Action Recognition" algorithms to detect boss attacks and react accordingly - Ask GPT about it
![image](https://github.com/FlawlessNa/Royals-V2/assets/106719178/c2620077-d36e-4a8d-b39b-f200a196cd2e)

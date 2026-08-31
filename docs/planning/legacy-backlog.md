# Legacy backlog

Archived notes, moved out of `README.md` and `NEW_README.md` when the repo root
was rewritten for new contributors. **Most of this is out of date** -- it is
kept for context on what was being considered, not as a work queue. Treat
anything here as a lead to verify against the current code, never as a
statement of how things are.

For work that is actually live, see GitHub Issues on `FlawlessNa/Legends`
(`docs/agents/issue-tracker.md`).

---

# Archived: README.md backlog

## Bug Fixes
- [ ] Looks like there's an existing bug between window switching and key releases
- [ ] For keys dependent on keyboard layout, such as "'", this can cause issues as the key doesn't do what it is intended to do in case of wrong layout
  - This is because the _keyboard_layout_handle is decorated with lru_cache
  - Can remove decorator, but function is somewhat slower (it is minimal though)
  - Still, it doesn't solve issue because if layout is wrong, the "'" should become "è" (as an example) and configs are therefore wrong in such a case
- [ ] Add a "log dump" from AttributeMetadata for each BotData instance upon engine shutdown
- [ ] There's a bug with the rotation cycle, could be caused by Mob Check failsafe, but rotation sometimes resets?
- [ ] Fix minimap error handling bug.
- [ ] Add ability to specify speed/jump from launcher
- [ ] When firing automated chat reaction, need to properly cancel all pending rotation/mobs hitting action, otherwise keystrokes in chat get mixed

## Model Usage
- [ ] For comparison, try removing the caching feature and assess which option is best
  - Use the BotData monitoring mechanism to do so
- [ ] Refactor model storage structure 
  - remove from .gitignore
  - instead of using models_paths, specify model name
  - make consistent structure for when we'll have lots of models
- [ ] Character detection: Remove the single detection param and instead return all positions.
  - Then, cross-validate with map objects to get each VR position, and compare with VR position estimated from minimap. Extract closest match.

## Map Parser
- [ ] Should be able to group footholds/ladders by actual "platforms" and "ladders" for pathfinding
- [ ] Can extract mobs and their "expected" locations to create synthetic data
- [ ] It can attempt to estimate the character's VR coordinates as well
- [ ] Should be able to draw proper background as well for synthetic data
- [ ] Apply edits on grid
- [ ] EditorView 2nd mob to show pathfinding and better finetuning with those
  - [ ] Ability to toggle jump/fall trajectories
  - [ ] Ability to show all connections for the current source node
  - [ ] Ability to print the path, movements and actions between source and dest nodes
  - [ ] mouse click to change source node, ctrl + click for target node
- [ ] New grid system: for jump connections, if needed, use VR physics/coordinates to determine if jump reaches other platform instead of approx minimap coordinates

## Movements
- [ ] Add step to convert current minimap pos towards closest walkable node, up to a small acceptable dist threshold
- [ ] Finetune translation of path -> movements -> actions + Rotation DM using Ludi FM map?
- [ ] custom-code for each "transition" from one movement to another
  - IDEA: Try using structural pattern matching (match-case statements) for more clarity
- [ ] When jump on rope is involved, ensure keys are forced released on all transitions up to jump on rope
- [ ] When target is reached (end of movement), force release keys
- [ ] there's clearly a "preference" to jump on rope from the right side, might want to figure out why?
- [ ] Ability for each MinimapGrid to fine-tune the calc_cost function
- [ ] Refactoring of movement_mechanics to be cleaner
- [ ] Finetune pathfinding weights/costs by looking at computed paths between source-target and adjust until it is optimal in most cases
- [ ] Connect map pathfinding Grid objects directly (see pathfinding docs/ documentation)

## Rotation
- [ ] Prevent attacking while close to a feature's edge

## Pause/Resume
- [ ] Streamline both pause/resume and disable/enable mechanism -> should only really be one. Make sure ref to tasks are properly updated too.
- [ ] implement keyboard sentinel for ability to pause all bots from keyboard
- [ ] third failsafe on rotation sentinels should trigger pausing mechanism (disable relevant decision makers)
- [ ] Keys are not necessarily released when paused; because release_keys is called too soon.
- [ ] Test the pauser/resumer for various scenarios (keep MobsHitting, Rebuffs, for testing purposes etc)

## Improvements
- [ ] Improve error management and handling for appropriate breakpoints and tracebacks (when error are somewhere else than within an engine)
- [ ] Rebuffing:
  - [ ] Handling of in-game Macros efficiently
   
- [ ] InventoryManager:
  - [ ] Confirmation of Door being cast properly (very easy in legends since there's an icon)
  - [ ] Breakdown of the class between interface components and actual decision-making
- [ ] transfer to GS2 under new framework?

## Other
- [ ] Kill switches that either:
    - Stops program
    - Return to lounge, then stops program
    - Exit client, then stops program
- [ ] Complete implementation of discord parser + unit tests
- [ ] Implement unit tests on entire botting library - use mocking such that test can run without the game environment
- [ ] Add logging everywhere -> use level 0 to disable thru a CONSTANT for each relevant script
- [ ] Look into leveraging psutil for performance monitoring of CPU resources by client/process
  - Also look into managing the Manager Process since it is a new feature that needs to spawn a process
- [ ] Look into using Profilers (cProfile, line_profiler) to identify bottlenecks in the code
- [ ] Look into using asyncio DEBUG mode (PYTHONASYNCIODEBUG=1) to identify potential issues with the code
- [ ] Look into leveraging loop.run_in_executor(concurrent.futures.ProcessPoolExecutor) for CPU-intensive operations?
- [ ] Make sure to refresh documentation everywhere

## DecisionMakers
- [ ] CheckStillAlive
- [ ] CheckStrangersInMap
- [ ] ChatMonitoring
  - When a relevant chat line is detected, minimize chat feed, scroll to that line and read it without any background noise.
  - Chat Parsing (try grayscale preprocessing on "general" lines) + GPT Automated Responses
  - Use dequeue structure
  - Idea: When detecting relevant lines, minimize chat and scroll up, then read that line without background noise
- [ ] Check for WhiteRoom (or any predominent color on-screen?) -> taken from GMS
- [ ] Check Remaining Potions, Pet Food, Mount Food, Magic Rocks
- [ ] Abnormal Status Detection (look for gray line types)
  - Stunned
  - Seduced
  - Cursed (reverse directions
- [ ] Check if straying too far from self.data.path? (Indicative of unexpected movements)
- [ ] GM Logo detection? (probably not realistic but could try)
    - Would need several screenshots, and threshold confirmed several times in a row.
- [ ] Inventory (mesos) parsing to ensure loot is still dropping from mobs

## Card Farming
- [ ] Draw each maps from game files (including backgrounds), then create synthetic by adding mobs at random (but reasonable) locations for their respective maps, then train a global "Mob" detection YOLO model (with 1 class for each mob)
- [ ] Once new game-file parser is done, make a launcher for card farming
  - Launcher requires a map, then use cv2 to show map. User can click on couple of points that will set the rotation.
  - At each point, the character will cast ult. and then move to the next point. Rinse and repeat until all cards done.
- [ ] Ultimately leverage the usual rotation/mobs-hitting decision-maker with a "global" mob-detection model
 
## Nice to have
  - [ ] for Ulu only - look into building an "unknown" object detection method, using UNKAD methodology or anomaly detection
  - [ ] for stationary farming - Can use a "pixel movement" detection instead of mob detection
  - [ ] Chat - Try additional pre-processing: Thresholding (improved?), Denoising (application of Gaussian and/or Median Blur), Contrast Enhancement (Make text more distinguishable from background)
  - [ ] Chat - Pre-trained model for semantic segmentation? Could help distinguish text from the rest.
  - [ ] Chat - Other OCR libraries? OCRopus & EasyOCR in particular.
  - [ ] Chat - Otherwise, build a modelling dataset with tons of chat lines and train a model to read text.
  - [ ] Bossing idea - use "Action Recognition" algorithms to detect boss attacks and react accordingly - Ask GPT about it (YOLOv8 for boss attacks?)
![image](https://github.com/FlawlessNa/Royals-V2/assets/106719178/c2620077-d36e-4a8d-b39b-f200a196cd2e)


---

# Archived: NEW_README.md backlog

## Botting System
- [ ] Ask Claude about the Mixin system and whether this can be improved or not really. Ask for a deep-dive on each existing Mixin implementation as well. 
- [ ] Look into Claude's advice of using a ProcessPoolExecutor to run all CPU-intensive functions (image processing, model detection, OCR, etc)
- [ ] Ask Claude to do additional toolkits script such as 
  - the measuring of bot interferences with respect to each other's loop cycle (see new-map-system branch)
  - Profiling of CV (cpu-bound) parallelism gains (see new-map-system branch)
- [ ] Ask Claude to look at the botting package step by step and see how it can be improved (the Process Model in general)
- [ ] Also look at each components individually to see if there are any recommandations, such as
  - Handling of Proxies
  - Decision Maker's request_proxy (proxy system) very convoluted (Enable/Disable mechanism overcomplicated)
  - BotData is "too magical"
  - Mixin system revamp if needed?
  - ActionRequest/TaskManager complexity? (Too many un-used features right now, such as re-queuing)
  - DecisionMaker does too much? (decision + coordination + proxy management) -> separation of concerns
  - Error Handling & Logging -> Need a centralized error recovery strategy, discord error notifications are currently ad-hoc
- [ ] Need to create a testing strategy and significantly expand toolkit scripts
  - Also delete obsolete ones

## Map Navigation
- [ ] Rework once again the navigation system, avoid using game files.
  - Look into navigation/ folder of new-map-system and ask Claude how to best tackle this
  - Minimap Creation GUI might be best

## Movements into Actions
- [ ] Ask Claude to compare new-map-system navigation with current, see what is best and if anything within new-map-system can be salvaged (make sure to mention we are moving away from anything related to game-files)

## Mob Detection
- [ ] Create a script to annotate a small number of images and pre-train a model
- [ ] Use that model's detection to create a larger annotated dataset and re-train a better model
- [ ] Look into a better mob detection model management (and combined with character detection)
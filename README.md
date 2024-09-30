# Royals-V2

## Bug Fixes
- [ ] Improvements of movements, particularly to avoid hitting while character is crouched
- [ ] Looks like there's an existing bug between window switching and key releases
- [ ] For keys dependent on keyboard layout, such as "'", this can cause issues as the key doesn't do what it is intended to do in case of wrong layout
  - This is because the _keyboard_layout_handle is decorated with lru_cache
  - Can remove decorator, but function is somewhat slower (it is minimal though)
  - Still, it doesn't solve issue because if layout is wrong, the "'" should become "è" (as an example) and configs are therefore wrong in such a case

- [ ] Test the pauser/resumer for various scenarios (keep MobsHitting, Rebuffs, for testing purposes etc)
  - Keys are not necessarily released when paused; because release_keys is called too soon.
  - [ ] third failsafe on rotation sentinels should trigger pausing mechanism (disable relevant decision makers)
  - Streamline both pause/resume and disable/enable mechanism -> should only really be one. Make sure ref to tasks are properly updated too.

- [ ] Improve error management and handling for appropriate breakpoints and tracebacks (when error are somewhere else than within an engine)
- [ ] Once MOB YOLO detection setup, try a new "smart" rotation algorithm based on scoring
  - score of 100 if 5 mobs in range of skill
  - score of 0 if no mobs in vision
  - user enters score which is then used to determine if hit mobs or rotate
  - score lowers as more distance with mobs
- [ ] there's clearly a "preference" to jump on rope from the right side, might want to figure out why?
  - Unless work on the new framework instead

## Model usage
- For Debug mode, use the result.plot() to show class name and confidence score as well.
- Transfer the model loading (from Character class) into InGameDetectionVisuals base class (and make sure characters as well as Mobs inherit from that new class).
- Add a method that parses each models_path and checks the available detection classes.
- models_path can be specified as a list or dict. Dict allows user to force a model for a given python class.
- List uses the parse method and returns the first model that is able to predict the python class (based on its class name) 
- Detection model for a given instance should be loaded only once, and then shared across all instances of the same class (classmethod)
  - This allows multi-bots to share same model instance (if they live in same Engine).
- [ ] Ability for each bot to share predictions through bot.data, for the usage of multiple decision makers
  - Add a auto-refreshing bot data attribute that runs each model after a threshold, and decision makers can use that data.
  - Relevant when multiple detected objects share the same model; since using model.predict() for all classes or only a subset takes roughly same exec. time
- [ ] Character detection: Remove the single detection param and instead return all positions.
  - Then, cross-validate with map objects to get each VR position, and compare with VR position estimated from minimap. Extract closest match.

## Improvements
- [ ] Rebuffing:
  - [ ] Handling of in-game Macros efficiently
   
- [ ] InventoryManager:
  - [ ] Confirmation of Door being cast properly
  - [ ] Breakdown of the class between interface components and actual decision-making

- Enabling/Disabling of DecisionMakers
- [ ] implement keyboard sentinel for ability to pause all bots from keyboard
- [ ] See if the pausing/resuming mechanism can leverage _disable and _enable_decision_makers functions.
  - They might need to be made staticmethods
  - They might need to be revamped to target specific bots
  - [ ] implement ability to use class' MRO to enable/disable decision makers
  - [ ] Implement ability to only target specific Bots (will be useful for Discord requests)
  - [ ] Better handling of the pausing system and disabling of decision makers. Those might be two different systems altogether.
    - Disabling/Enabling would be for normal course of bot operations.
    - Ability to use self_only params, but not for all decision makers (Ex: PartyRebuff cannot be disabled for a single char)
    - Pausing would be specifically for user-requests

- [ ] Movement_mechanics (original system):
  - Ability for each MinimapGrid to fine-tune the calc_cost function
  - 
- [ ] Movement mechanics (new system):
  - Find objects and potentially tiles on the screen that can be used as reference points for movement
  - Modify map parser translation into vr coordinates function -> no need for a transfo matrix, just a simple translation.
  - Solution 1:
    - Can either use ORB feature matching or template matching to find them
    - Can use optical flow to track movement of these objects
  - Solution 2:
    - Re-build an annotated dataset with each objects, use YOLO model tracking mode to track them
    - Try using GPU for faster processing?
  - Use known on-screen location of objects, combined with known VR coordinates, and known on-screen location of character, to determine VR coordinates of character
  - Refactor pathing/movements/actions to use VR coordinates instead of minimap coordinates
  - Note: This might require to properly code all physics standard kinetic equations as well
- [ ] Code the movement calibration toolkit to help improvement transitions from path into movements into actions
- [ ] transfer to GS2 under new framework?

### Other
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

### DecisionMakers
- [ ] CheckStillAlive
- [ ] CheckStrangersInMap
- [ ] ChatMonitoring
  - When a relevant chat line is detected, minimize chat feed, scroll to that line and read it without any background noise.
  - Chat Parsing (try grayscale preprocessing on "general" lines) + GPT Automated Responses
  - Use dequeue structure
  - Idea: When detecting relevant lines, minimize chat and scroll up, then read that line without background noise
- [ ] CheckStillInMap
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

### Card Farming
- [ ] Once new game-file parser is done, make a launcher for card farming
  - Launcher requires a map, then use cv2 to show map. User can click on couple of points that will set the rotation.
  - At each point, the character will cast ult. and then move to the next point. Rince and repeat until all cards done.

### Pathing
- [ ] Refactoring of movement_mechanics to be cleaner
- [ ] Finetune pathfinding weights/costs by looking at computed paths between source-target and adjust until it is optimal in most cases
- [ ] Connect map pathfinding Grid objects directly (see pathfinding docs/ documentation)
- [ ] Look into game files to reverse engineer movements for better precision
  - Can definitely use VRTop, VRLeft, VRBottom, VBRRight to convert minimap coordinates into actual map coordinates
- [ ] (least priority) Rotation decision maker cancels itself when stray too far from path

## Nice to have
  - [ ] for Ulu only - look into building an "unknown" object detection method, using UNKAD methodology or anomaly detection
  - [ ] for stationary farming - Can use a "pixel movement" detection instead of mob detection
  - [ ] Chat - Try additional pre-processing: Thresholding (improved?), Denoising (application of Gaussian and/or Median Blur), Contrast Enhancement (Make text more distinguishable from background)
  - [ ] Chat - Pre-trained model for semantic segmentation? Could help distinguish text from the rest.
  - [ ] Chat - Other OCR libraries? OCRopus & EasyOCR in particular.
  - [ ] Chat - Otherwise, build a modelling dataset with tons of chat lines and train a model to read text.
  - [ ] Bossing idea - use "Action Recognition" algorithms to detect boss attacks and react accordingly - Ask GPT about it (YOLOv8 for boss attacks?)
![image](https://github.com/FlawlessNa/Royals-V2/assets/106719178/c2620077-d36e-4a8d-b39b-f200a196cd2e)

# Royals-V2

## Bug Fixes
- [ ] Looks like there's an existing bug between window switching and key releases
- [ ] For keys dependent on keyboard layout, such as "'", this can cause issues as the key doesn't do what it is intended to do in case of wrong layout
  - This is because the _keyboard_layout_handle is decorated with lru_cache
  - Can remove decorator, but function is somewhat slower (it is minimal though)
  - Still, it doesn't solve issue because if layout is wrong, the "'" should become "è" (as an example) and configs are therefore wrong in such a case

## Model Usage
- [ ] Refactor model storage structure 
  - remove from .gitignore
  - instead of using models_paths, specify model name
  - make consistent structure for when we'll have lots of models
- For Debug mode, use result.plot() to show class name and confidence score as well.
- For Debug mode, the attack range around character should be a square drawn on the debug screen.
- [ ] Ability for each bot to share predictions
- [ ] Character detection: Remove the single detection param and instead return all positions.
  - Then, cross-validate with map objects to get each VR position, and compare with VR position estimated from minimap. Extract closest match.

## Map Parser
- [ ] Class that can be used to draw canvas for ANY map (provided the .xml files are available)
  - VR Map Canvas
  - VR Foothold Canvas
  - VR Minimap Canvas
  - Minimap Canvas
- [ ] It also extracts objects/tiles
- [ ] It can write a .py file that describes a minimap. This can be loaded and used when fine-tuning of weights/costs is necessary
  - Requires interactive window where user enters feature names for interesting features
  - Unnecessary features are given sequential generic names
- [ ] It can attempt to estimate the character's VR coordinates as well

## Movements
- [ ] Finetune translation of path -> movements -> actions + Rotation DM using Ludi FM map?
- [ ] When jump on rope is involved, ensure keys are forced released on all transitions up to jump on rope
- [ ] there's clearly a "preference" to jump on rope from the right side, might want to figure out why?
- [ ] Ability for each MinimapGrid to fine-tune the calc_cost function
- [ ] Movement mechanics (new system):
  - Find objects and potentially tiles on the screen that can be used as reference points for movement
  - Solution 1:
    - Can either use ORB feature matching or template matching to find them
    - Can use optical flow to track movement of these objects
  - Use known on-screen location of objects, combined with known VR coordinates, and known on-screen location of character, to determine VR coordinates of character
  - Refactor pathing/movements/actions to use VR coordinates instead of minimap coordinates
  - Note: This might require to properly code all physics standard kinetic equations as well
- [ ] Code the movement calibration toolkit to help improvement transitions from path into movements into actions
- [ ] Refactoring of movement_mechanics to be cleaner
- [ ] Finetune pathfinding weights/costs by looking at computed paths between source-target and adjust until it is optimal in most cases
- [ ] Connect map pathfinding Grid objects directly (see pathfinding docs/ documentation)

## Rotation
- [ ] Once MOB YOLO detection setup, try a new "smart" rotation algorithm based on scoring
  - score of 100 if 5 mobs in range of skill
  - score of 0 if no mobs in vision
  - user enters score which is then used to determine if hit mobs or rotate
  - score lowers as more distance with mobs
  - Determine an on-screen point to rotate to. Convert this into approximate Minimap VR location, then into minimap location.

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
  - [ ] Confirmation of Door being cast properly
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
- [ ] Once new game-file parser is done, make a launcher for card farming
  - Launcher requires a map, then use cv2 to show map. User can click on couple of points that will set the rotation.
  - At each point, the character will cast ult. and then move to the next point. Rinse and repeat until all cards done.

## Nice to have
  - [ ] for Ulu only - look into building an "unknown" object detection method, using UNKAD methodology or anomaly detection
  - [ ] for stationary farming - Can use a "pixel movement" detection instead of mob detection
  - [ ] Chat - Try additional pre-processing: Thresholding (improved?), Denoising (application of Gaussian and/or Median Blur), Contrast Enhancement (Make text more distinguishable from background)
  - [ ] Chat - Pre-trained model for semantic segmentation? Could help distinguish text from the rest.
  - [ ] Chat - Other OCR libraries? OCRopus & EasyOCR in particular.
  - [ ] Chat - Otherwise, build a modelling dataset with tons of chat lines and train a model to read text.
  - [ ] Bossing idea - use "Action Recognition" algorithms to detect boss attacks and react accordingly - Ask GPT about it (YOLOv8 for boss attacks?)
![image](https://github.com/FlawlessNa/Royals-V2/assets/106719178/c2620077-d36e-4a8d-b39b-f200a196cd2e)

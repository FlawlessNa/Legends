# Royals-V2

## Bug Fixes
- [ ] Improve client_handler to avoid need of updating window title on every game update
- [ ] Improvements of movements, particularly to avoid hitting while character is crouched
- [ ] Looks like there's an existing bug between window switching and key releases
- [ ] For keys dependent on keyboard layout, such as "'", this can cause issues as the key doesn't do what it is intended to do in case of wrong layout
  - This is because the _keyboard_layout_handle is decorated with lru_cache
  - Can remove decorator, but function is somewhat slower (it is extremely minimal though)
  - Still, it doesn't solve issue because if layout is wrong, the "'" should become "è" (as an example) and configs are therefore wrong in such  a case

## Improvements
- [ ] Rebuffing:
  - [ ] Handling of in-game Macros efficiently
   
- [ ] InventoryManager:
  - [ ] Confirmation of Door being cast properly
  - [ ] Breakdown of the class between interface components and actual decision-making

- [ ] third failsafe on rotation sentinels should trigger pausing mechanism (disable relevant decision makers)
- Enabling/Disabling of DecisionMakers 
  - [ ] implement ability to use class' MRO to enable/disable decision makers
  - [ ] Implement ability to only target specific Bots (will be useful for Discord requests)
  - [ ] Better handling of the pausing system and disabling of decision makers. Those might be two different systems altogether.
    - Disabling/Enabling would be for normal course of bot operations.
    - Ability to use self_only params, but not for all decision makers (Ex: PartyRebuff cannot be disabled for a single char)
    - Pausing would be specifically for user-requests

- [ ] DiscordParser
  - Implement an additional task within each Engine process (for each bot individually) (ex) that sentinels a specific multiprocessing.Event flag to pause/resume the bot
  - use keyboard.add_hotkey + keyboard.wait to set/clear the flag
  - The mainprocess has an additional task that sentinels a specific keyboard input to set/clear the flag
  - That same multiprocessing.Event flag can be used for discord requests to pause/resume
  - Convert _disable_decision_makers (and _enable) into staticmethods that can be used from mainProcess as well

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
- [ ] Mob Check -> with 2-3 layers reactions?
- [ ] CheckStillAlive
- [ ] CheckStrangersInMap
- [ ] ChatMonitoring
  - When a relevant chat line is detected, minimize chat feed, scroll to that line and read it without any background noise.
- [ ] Check for WhiteRoom (or any predominent color on-screen?) -> taken from GMS
  - Chat Parsing (try grayscale preprocessing on "general" lines) + GPT Automated Responses
  - Use dequeue structure
  - Idea: When detecting relevant lines, minimize chat and scroll up, then read that line without background noise
- [ ] CheckStillInMap
- [ ] Check Remaining Potions, Pet Food, Mount Food, Magic Rocks
- [ ] Abnormal Status Detection (look for gray line types)
  - Stunned
  - Seduced
  - Cursed (reverse directions
- [ ] Check if straying too far from self.data.path? (Indicative of unexpected movements)
- [ ] GM Logo detection? (probably not realistic but could try)
    - Would need several screenshots, and threshold confirmed several times in a row.
- [ ] Inventory (mesos) parsing to ensure loot is still dropping from mobs

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

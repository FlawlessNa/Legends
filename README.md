# Royals-V2

## TODO
- [ ] Generic Generator class for the botting library + incorporated failsafe methods
-  [ ] Add failsafe on MobHitting?
-  [ ] Add failsafe on Rebuff?
- [ ] Add a generic RotationGenerator for re-usable functions and methods
- [ ] Anti Detection Features -> Features are monitored in the child processes, but reactions and coordinations between clients done in Main
  - [ ] Chat Parsing + Automated Responses
  - [ ] Blue Notification detection (chat invite, other invites, etc)
  - [ ] Minimap Parsing for strangers + random reaction
  - [ ] Minimap Parsing for unexpected self movements + random reaction
  - [ ] Minimap parsing to ensure still in proper map + random reaction
  - [ ] Mob freeze (from a GM) + random reaction
  - [ ] Inventory (mesos) parsing to ensure loot is still dropping from mobs + random reaction
  - [ ] GM Logo detection
  - [ ] Nice-to-have, for Ulu only - look into building an "unknown" object detection method, using UNKAD methodology
- [x] Significant improvements required to Character detection - detection needs to be more stable
  - [ ] Standardize code and transfer detection framework into botting library
- [ ] Implement better handling of QueueAction Priority
- Significant improvements required to Mob detection
  - [ ] Add pre-processing techniques such as minimal nbr of detection to be considered a mob
  - [ ] Clean the pre-processing to remove the additional layer of the filter function
  - [ ] Define additional generic detection functions for mobs
  - [ ] [Optional] combine with their HP bar
- [ ] Improvements to the QueueAction wrapping/management
- [ ] Improvements to RoyalsData management (split into subclasses)
- [ ] Add slice creation from box objects used to crop a numpy array (considers the client margins as well)
- [ ] Skill Specs Finder
- [ ] Major clean-up of the Royals library
- [ ] When done, update all docstrings as some are lacking now.
  - [ ] Botting.core
  - [ ] Royals
- [ ] Enable np arrays/.png files to be sent through Pipe - then send chat images towards discord
- [ ] Generic Failsafe framework (for normal scenarios, NOT for anti-detection)
  - [ ] Generic expression to evaluate (time-based, attempts-based, or other)
- [ ] Emergency triggers
  - [ ] Course of action when any error is encountered, before program exists
- [ ] GPT Automated Responses
- [ ] For chat lines reading, try converting to gray and applying simple thresholding (general lines at least)
- [ ] Mouse movements and mouse clicks
- [ ] Finalize Discord communications
- [ ] Refactor game interface more accurately
  - [ ] Quickslots
  - [ ] Inventory
  - [ ] Level up detection
  - [ ] Ability Points assignment
- [ ] UnitTests on the botting library

## Nice to have
  - [ ] Chat - Try additional pre-processing: Thresholding (improved?), Denoising (application of Gaussian and/or Median Blur), Contrast Enhancement (Make text more distinguishable from background)
  - [ ] Chat - Pre-trained model for semantic segmentation? Could help distinguish text from the rest.
  - [ ] Chat - Other OCR libraries? OCRopus & EasyOCR in particular.
  - [ ] Chat - Otherwise, build a modelling dataset with tons of chat lines and train a model to read text.
  - [ ] Bossing idea - use "Action Recognition" algorithms to detect boss attacks and react accordingly - Ask GPT about it
![image](https://github.com/FlawlessNa/Royals-V2/assets/106719178/c2620077-d36e-4a8d-b39b-f200a196cd2e)

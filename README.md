# Royals-V2

## TODO
- Debug windows should appear on every call for 'continuous' debugging
- Smart Rotation
  - [ ] Idea - When new platform reached, cover x% of the platform while blindly attacking, then converge into mid-ish platform. Then, wait until Y seconds without any mob detection before next rotation
- [ ] Significant improvements required to Character detection - detection needs to be more stable
  - [x] Re-do detection using current framework
  - [x] Add 20+ Pos/Neg imgs for each map coded with mobs & skill animations and retrain model (In progress)
  - [ ] Standardize code and transfer detection framework into botting library
- Significant improvements required to Mob detection
  - [ ] Add pre-processing techniques such as minimal nbr of detection to be considered a mob
  - [ ] Clean the pre-processing to remove the additional layer of the filter function
  - [ ] Define additional generic detection functions for mobs
  - [ ] [Optional] combine with their HP bar
- [ ] Generic Generator class for the botting library + incorporated failsafe methods
- [ ] Improvements to the QueueAction wrapping
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
  - [x] Watch for no pathing
  - [ ] Watch for no movements when movement is expected, add actions to solve when that happens
- [ ] Emergency triggers
  - [ ] Course of action when any error is encountered, before program exists
- [ ] Anti Detection Features -> Features are monitored in the child processes, but reactions and coordinations between clients done in Main
  - [ ] Chat Parsing + Automated Responses
  - [ ] Minimap Parsing for strangers + random reaction
  - [ ] Minimap Parsing for unexpected self movements + random reaction
  - [ ] Minimap parsing to ensure still in proper map + random reaction
  - [ ] Mob freeze (from a GM) + random reaction
  - [ ] Inventory (mesos) parsing to ensure loot is still dropping from mobs + random reaction
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

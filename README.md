# Royals-V2

## TODO

### Leeching Engine
  - [ ] Rebuffing from Leechers
  - [ ] Ultimate Cast failsafe - check if MP has changed by at least X%
  
### Generators
  - [ ] Check character still alive
  - [ ] Check Potions Pet Food, Mount Food
  - [ ] Cooldown buffs
  - [ ] Inventory Management
    - [x] Basic parser to check space left
    - [ ] Advanced parser to check stats on each item
  - [x] Automated AP distribution
  - [x] Generic Generator class for botting library
  - [ ] Add failsafe on MobHitting (how??)
  - [ ] Add failsafe on Rebuff (look for fresh buff icon in top right screen)
  - [ ] Add failsafe on any Rotation Generators - Movement is expected if action is not cancelled

### Anti Detection Features
  - [ ] Chat Parsing (try grayscale preprocessing on "general" lines) + GPT Automated Responses
  - [ ] GM Logo detection
  - [ ] Abnormal Status Detection (look for gray line types)
  - [ ] Minimap Parsing to ensure still in proper map + random reaction
  - [ ] Minimap Parsing for strangers + random reaction
  - [ ] Minimap Parsing for unexpected self movements + random reaction
  - [ ] Blue Notification detection (chat invite, other invites, etc)
  - [x] Mob freeze (from a GM) + random reaction
  - [ ] Inventory (mesos) parsing to ensure loot is still dropping from mobs + random reaction
  - [ ] For complex movements (teleport, telecast, etc), use Spy++ to find exact key combinations when done by human, and make sure to properly replicate (should be very easy)
  - [ ] Nice-to-have, for Ulu only - look into building an "unknown" object detection method, using UNKAD methodology or anomaly detection
  
### Character detection
  - [ ] Standardize code and transfer detection framework into botting library
  
### QueueAction
  - [ ] Implement better handling of QueueAction Priority
  - [ ] Added action attributes to enable IPC
  
### Mob detection
  - [ ] Clean the pre-processing to remove the additional layer of the filter function
  - [ ] Define additional generic detection functions for mobs
  - [ ] Combine with HP bar
  
### RoyalsData Management
  - [x] Split into several subclasses, each specific to a generator
  - [ ] Add a PerformanceData class for monitoring (mesos/h, exp/h, etc)
  - [x] DecisionEngine should not have to update anything. Each Generator should deal with their own requirements.

### Error Management
  - [ ] Ability to close all clients if error occurs
  - [ ] Ability to send all characters to lounge if error occurs

### Misc
  - [ ] Add slice creation from box objects used to crop a numpy array (considers the client margins as well)
  - [ ] Skill Specs Finder
  - [x] Mouse movements and mouse clicks
  - [ ] Finalize Discord communications - Control of which process are to respond to user commands
  - [ ] UnitTests on the botting library

### Documentation
  - [ ] Botting.core
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

# Royals-V2

## TODO

### Leeching Engine
  - [ ] Rebuffing from Leechers
  - [ ] Ultimate Cast failsafe - check if MP has changed by at least X%
  
### Maintenance Generators
  - [ ] Check character still alive
  - [ ] Check Potions Pet Food, Mount Food
  - [ ] Cooldown buffs
  - [ ] Inventory Management
  - [x] Automated AP distribution
  
### Generic Generator class for the botting library + incorporated failsafe methods
  - [ ] Add failsafe on MobHitting
  - [ ] Add failsafe on Rebuff
  - [ ] Add failsafe on any Rotation Generators - Movement is expected if action is not cancelled

### Anti Detection Features
  - [ ] Chat Parsing (try grayscale preprocessing on "general" lines) + GPT Automated Responses
  - [ ] Abnormal Status Detection (look for gray line types)
  - [ ] Minimap Parsing for strangers + random reaction
  - [ ] Minimap Parsing for unexpected self movements + random reaction
  - [ ] Minimap parsing to ensure still in proper map + random reaction
  - [ ] Blue Notification detection (chat invite, other invites, etc)
  - [ ] Mob freeze (from a GM) + random reaction
  - [ ] Inventory (mesos) parsing to ensure loot is still dropping from mobs + random reaction
  - [ ] GM Logo detection
  - [ ] For complex movements (teleport, telecast, etc), use Spy++ to find exact key combinations when done by human, and make sure to properly replicate (should be very easy)
  - [ ] Nice-to-have, for Ulu only - look into building an "unknown" object detection method, using UNKAD methodology
  
### Character detection
  - [ ] Standardize code and transfer detection framework into botting library
  
### QueueAction Prioritization
  - [ ] Implement better handling of QueueAction Priority
  
### Mob detection
  - [ ] Clean the pre-processing to remove the additional layer of the filter function
  - [ ] Define additional generic detection functions for mobs
  - [ ] Combine with their HP bar
  
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
  - [ ] Finalize Discord communications
  - [ ] UnitTests on the botting library

### Documentation
  - [ ] Botting.core
  - [ ] Royals (entire package)

### Game Interface
  - [ ] Quickslots
  - [ ] Inventory
  - [ ] Level up detection

## Nice to have
  - [ ] Chat - Try additional pre-processing: Thresholding (improved?), Denoising (application of Gaussian and/or Median Blur), Contrast Enhancement (Make text more distinguishable from background)
  - [ ] Chat - Pre-trained model for semantic segmentation? Could help distinguish text from the rest.
  - [ ] Chat - Other OCR libraries? OCRopus & EasyOCR in particular.
  - [ ] Chat - Otherwise, build a modelling dataset with tons of chat lines and train a model to read text.
  - [ ] Bossing idea - use "Action Recognition" algorithms to detect boss attacks and react accordingly - Ask GPT about it
![image](https://github.com/FlawlessNa/Royals-V2/assets/106719178/c2620077-d36e-4a8d-b39b-f200a196cd2e)

# Royals-V2

## TODO
- [x] Implement Skills
- [ ] Skill Specs Finder
- [ ] Switch back to a single Rotation Lock and coordination between rotation generators
- [ ] Significant improvements required to Mob detection - combine with their HP bar, DMG display, and model
- [ ] Significant improvements required to Character detection - detection needs to be more stable
- [ ] Improvements to the QueueAction wrapping
- [ ] Generic Failsafe framework
- [ ] Improvements to RoyalsData management
- [ ] Add slice creation from box objects used to crop a numpy array (considers the client margins as well)
- [ ] Major clean-up of the Royals library
- [ ] When done, update all docstrings as some are lacking now.
  - [ ] Botting.core
  - [ ] Royals
- [ ] Enable np arrays/.png files to be sent through Pipe - then send chat images towards discord
- [ ] Failsafes
  - [ ] Watch for no movements when movement is expected, add actions to solve when that happens
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
- [ ] Character detection - model improvement, gather more data
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
![image](https://github.com/FlawlessNa/Royals-V2/assets/106719178/c2620077-d36e-4a8d-b39b-f200a196cd2e)

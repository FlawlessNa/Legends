# Royals-V2

## TODO
- [ ] Character detection
  - [ ] Combine with Mob detection and skill range to determine if a mob is in range
- [x] Remove Asyncio.PriorityQueue and bypass by simply using the mp.Queue
- [x] RoyalsData - Should be instanciated within BotMonitor (child process) and updated from there.
- [x] Automated handle and IGN associated + retrieval
- [ ] Enable np arrays/.png files to be sent through Pipe - then send chat images towards discord
- [ ] Anti Detection Features -> Features are monitored in the child processes, but reactions and coordinations between clients done in Main
  - [ ] Chat Parsing + Automated Responses
  - [ ] Minimap Parsing for strangers + random reaction
  - [ ] Minimap Parsing for unexpected self movements + random reaction
  - [ ] Minimap parsing to ensure still in proper map + random reaction
  - [ ] Mob freeze (from a GM) + random reaction
  - [ ] Inventory (mesos) parsing to ensure loot is still dropping from mobs + random reaction
- [ ] GPT Automated Responses
- [ ] For chat lines reading, try converting to gray and applying simple thresholding (general lines at least)
- [ ] When done, update all docstrings as some are lacking now.
- [ ] Minimap Parsing - "Draw" the minimap canvas while YOU manually move around the entire map. Then, translate drawings into features and adjust.
- [ ] Mouse movements and mouse clicks
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

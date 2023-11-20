# Royals-V2

## TODO
- [x] Refactor Package more appropriately - there should be a "botting" library and a "royals" implementation.
- [ ] Minimap pathing
  - [ ] Clean minimap class structure and grid constructor (Add a Feature subclass of Box??)
  - [ ] algorithm to find paths between point A and B based on minimap
  - [ ] Translate path to movements
- [ ] Automated handle and IGN associated + retrieval
- [ ] Enable np arrays/.png files to be sent through Pipe - then send chat images towards discord
- [ ] GPT Automated Responses
- [ ] Character detection
  - [ ] Combine with Mob detection and skill range to determine if a mob is in range
- [ ] When done, update all docstrings as some are lacking now.
- [ ] Mouse movements and mouse clicks
- [ ] Refactor game interface more accurately
  - [ ] Quickslots
  - [ ] Inventory
  - [ ] Level up detection
  - [ ] Ability Points assignment
- [ ] Common actions
  - [ ] Jumping on a rope/ladder
  - [ ] Jumping from a platform to another
- [ ] UnitTests on the botting library

## Nice to have
  - [ ] Chat - Try additional pre-processing: Thresholding (improved?), Denoising (application of Gaussian and/or Median Blur), Contrast Enhancement (Make text more distinguishable from background)
  - [ ] Chat - Pre-trained model for semantic segmentation? Could help distinguish text from the rest.
  - [ ] Chat - Other OCR libraries? OCRopus & EasyOCR in particular.
  - [ ] Chat - Otherwise, build a modelling dataset with tons of chat lines and train a model to read text.
![image](https://github.com/FlawlessNa/Royals-V2/assets/106719178/c2620077-d36e-4a8d-b39b-f200a196cd2e)

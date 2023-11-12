# Royals-V2

## TODO
- [x] Refactor Bot - All bots into a single Async Queue, each bot has a subprocess for Monitoring. Game Status is updated through monitoring as well.
  - [ ] When done, update all docstrings as some are lacking now.
  - [x] Also, add task cancellation based on their priority - especially important for controller.move
- [ ] Refactor game interface more accurately
- [ ] Enable np arrays/.png files to be sent through Pipe - then send chat images towards discord
- [ ] GPT Automated Responses
- [ ] Automated handle and IGN associated + retrieval
- [ ] Minimap pathing - algorithm to find paths between point A and B based on minimap
- [ ] Refactor QueueActions for additional capabilities
- [ ] Common actions

## Nice to have
  - [ ] Chat - Try additional pre-processing: Thresholding (improved?), Denoising (application of Gaussian and/or Median Blur), Contrast Enhancement (Make text more distinguishable from background)
  - [ ] Chat - Pre-trained model for semantic segmentation? Could help distinguish text from the rest.
  - [ ] Chat - Other OCR libraries? OCRopus & EasyOCR in particular.
  - [ ] Chat - Otherwise, build a modelling dataset with tons of chat lines and train a model to read text.
  - [ ] Object Detection Modelling - For Characters (Generally), My characters (if required), Mobs (1 model per mob)
![image](https://github.com/FlawlessNa/Royals-V2/assets/106719178/c2620077-d36e-4a8d-b39b-f200a196cd2e)

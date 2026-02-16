## Botting System
- [ ] Look into Claude's advice of using a ProcessPoolExecutor to run all CPU-intensive functions (image processing, model detection, OCR, etc)
- [ ] Ask Claude to do additional toolkits script such as 
  - the measuring of bot interferences with respect to each other's loop cycle (see new-map-system branch)
  - Profiling of CV (cpu-bound) parallelism gains (see new-map-system branch)
- [ ] Ask Claude to look at the botting package step by step and see how it can be improved (the Process Model in general)
- [ ] Also look at each components individually to see if there are any recommandations, such as
  - Decision Maker's request_proxy (proxy system) very convoluted (Enable/Disable mechanism overcomplicated)
  - BotData is "too magical"
  - ActionRequest/TaskManager complexity? (Too many un-used features right now, such as re-queuing)
  - DecisionMaker does too much? (decision + coordination + proxy management) -> separation of concerns
  - Error Handling & Logging -> Need a centralized error recovery strategy, discord error notifications are currently ad-hoc
- [ ] Need to create a testing strategy and significantly expand toolkit scripts
  - Also delete obsolete ones

## Map Navigation
- [ ] Rework once again the navigation system, avoid using game files.
  - Look into navigation/ folder of new-map-system and ask Claude how to best tackle this


## Mob Detection
- [ ] Create a script to annotate a small number of images and pre-train a model
- [ ] Use that model's detection to create a larger annotated dataset and re-train a better model
- [ ] Look into a better mob detection model management (and combined with character detection)
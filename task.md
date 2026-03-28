# Task: INC Driver Dashboard Enhancements

## Feature 1: Add Directions to Driver Dashboard
- [ ] Backend: Add `directions` field to `/api/driver/status` response
- [ ] Backend: Include `directions` in WebSocket driver push
- [ ] Frontend: Create `DirectionsBanner` component
- [ ] Frontend: Add `DirectionInfo` type, integrate into [App.tsx](file:///c:/Users/ASUS/Downloads/INC/frontend/admin-dashboard/src/App.tsx)

## Feature 2: Fix Start and Destination Node Display
- [ ] Backend: Add `start_node`/`destination_node` to driver API responses
- [ ] Frontend: Update [RouteProgress](file:///c:/Users/ASUS/Downloads/INC/frontend/driver-dashboard/src/components/RouteProgress.tsx#10-83) with START/DEST labels
- [ ] Frontend: Update [InstructionBanner](file:///c:/Users/ASUS/Downloads/INC/frontend/driver-dashboard/src/components/InstructionBanner.tsx#16-33) with From→To route info
- [ ] Frontend: Update [CorridorStatus](file:///c:/Users/ASUS/Downloads/INC/frontend/driver-dashboard/src/components/CorridorStatus.tsx#11-57) to highlight start/dest

## Feature 3: Post-Arrival Baseline Comparison
- [ ] Backend: Add `/api/driver/arrival-comparison/{run_id}` endpoint
- [ ] Frontend: Create `BaselineComparison` component with loading state ("Computing fixed baseline...")
- [ ] Frontend: Integrate into arrived screen in [App.tsx](file:///c:/Users/ASUS/Downloads/INC/frontend/admin-dashboard/src/App.tsx)

## Feature 4: Fix Speed Buttons
- [ ] Change speed options from 1x/5x/10x/20x to 1x/2x/5x only
- [ ] Ensure speed buttons actually work

## Feature 5: Add Maximum Time Setting in Admin Config
- [ ] Backend: Add max_time_minutes config parameter
- [ ] Frontend: Add max time input in admin Configuration page

## Verification
- [ ] Run existing tests: `python -m pytest backend/tests/ -q`
- [ ] Add new tests for new endpoints
- [ ] Manual browser verification

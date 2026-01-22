from datetime import datetime, timedelta

from module.equipment.assets import EQUIPMENT_OPEN
from module.exception import ScriptError
from module.logger import logger
from module.map.map_grids import SelectedGrids
from module.notify import handle_notify
from module.os.assets import FLEET_FLAGSHIP
from module.os.map import OSMap
from module.os.ship_exp import ship_info_get_level_exp
from module.os.ship_exp_data import LIST_SHIP_EXP
from module.os_handler.action_point import ActionPointLimit


class OpsiHazard1Leveling(OSMap):
    def os_hazard1_leveling(self):
        logger.hr('OS hazard 1 leveling', level=1)
        # Without these enabled, CL1 gains 0 profits
        self.config.override(
            OpsiGeneral_DoRandomMapEvent=True,
        )
        if self.config.OpsiHazard1Leveling_ConnectedToMeowfficerFarming and not self.config.is_task_enabled('OpsiMeowfficerFarming'):
            self.config.cross_set(keys='OpsiMeowfficerFarming.Scheduler.Enable', value=True)
        while True:
            # Limited action point preserve of hazard 1 to 200
            self.config.OS_ACTION_POINT_PRESERVE = 200
            if self.config.is_task_enabled('OpsiAshBeacon') \
                    and not self._ash_fully_collected \
                    and self.config.OpsiAshBeacon_EnsureFullyCollected:
                logger.info('Ash beacon not fully collected, ignore action point limit temporarily')
                self.config.OS_ACTION_POINT_PRESERVE = 0
            logger.attr('OS_ACTION_POINT_PRESERVE', self.config.OS_ACTION_POINT_PRESERVE)

            if self.get_yellow_coins() < self.config.OpsiHazard1Leveling_YellowCoinPreserve:
                logger.info(f'Reach the limit of yellow coins, preserve={self.config.OpsiHazard1Leveling_YellowCoinPreserve}')
                if self.config.OpsiHazard1Leveling_ConnectedToMeowfficerFarming:
                    with self.config.multi_set():
                        self.config.task_delay(server_update=True)
                        if not self.is_in_opsi_explore():
                            cd = self.nearest_task_cooling_down
                            if cd is None:
                              for task in ['OpsiAbyssal', 'OpsiStronghold', 'OpsiObscure']:
                                  if self.config.is_task_enabled(task):
                                     self.config.task_call(task)
                            self.config.task_call('OpsiMeowfficerFarming')
                self.config.task_stop()

            self.get_current_zone()

            # Preset action point to 70
            # When running CL1 oil is for running CL1, not meowfficer farming
            keep_current_ap = True
            if self.config.OpsiGeneral_BuyActionPointLimit > 0:
                keep_current_ap = False
            self.action_point_set(cost=70, keep_current_ap=keep_current_ap, check_rest_ap=True)
            if self._action_point_total >= self.config.OpsiHazard1Leveling_ActionPointPreserve and self.config.OpsiHazard1Leveling_SurplusActionPointMeowfficerFarming and self.config.OpsiHazard1Leveling_ConnectedToMeowfficerFarming:
                with self.config.multi_set():
                    self.config.task_delay(server_update=True)
                    if not self.is_in_opsi_explore():
                        cd = self.nearest_task_cooling_down
                        if cd is None:
                            for task in ['OpsiAbyssal', 'OpsiStronghold', 'OpsiObscure']:
                                if self.config.is_task_enabled(task):
                                    self.config.task_call(task)
                        self.config.task_call('OpsiMeowfficerFarming')
                self.config.task_stop()

            if self.config.OpsiHazard1Leveling_TargetZone != 0:
                zone = self.config.OpsiHazard1Leveling_TargetZone
            else:
                zone = 22
            logger.hr(f'OS hazard 1 leveling, zone_id={zone}', level=1)
            if self.zone.zone_id != zone or not self.is_zone_name_hidden:
                self.globe_goto(self.name_to_zone(zone), types='SAFE', refresh=True)
            self.fleet_set(self.config.OpsiFleet_Fleet)
            self.run_strategic_search()

            if self.config.OpsiHazard1Leveling_ExecuteFixedPatrolScan:
                exec_fixed = getattr(self.config, 'OpsiHazard1Leveling_ExecuteFixedPatrolScan', False)
                if exec_fixed:
                    self._execute_fixed_patrol_scan(ExecuteFixedPatrolScan=True)

            self.handle_after_auto_search()
            solved_events = getattr(self, '_solved_map_event', set())
            if 'is_akashi' in solved_events:
                try:
                    from datetime import datetime
                    key = f"{datetime.now():%Y-%m}-akashi"
                    data = self._load_cl1_monthly()
                    data[key] = int(data.get(key, 0)) + 1
                    self._save_cl1_monthly(data)
                    logger.attr('cl1_akashi_monthly', data[key])
                except Exception:
                    logger.exception('Failed to persist CL1 akashi monthly count')

            self.config.check_task_switch()

    def os_check_leveling(self):
        logger.hr('OS check leveling', level=1)
        logger.attr('OpsiCheckLeveling_LastRun', self.config.OpsiCheckLeveling_LastRun)
        time_run = self.config.OpsiCheckLeveling_LastRun + timedelta(days=1)
        logger.info(f'Task OpsiCheckLeveling run time is {time_run}')
        if datetime.now().replace(microsecond=0) < time_run:
            logger.info('Not running time, skip')
            return
        target_level = self.config.OpsiCheckLeveling_TargetLevel
        if not isinstance(target_level, int) or target_level < 0 or target_level > 125:
            logger.error(f'Invalid target level: {target_level}, must be an integer between 0 and 125')
            raise ScriptError(f'Invalid opsi ship target level: {target_level}')
        if target_level == 0:
            logger.info('Target level is 0, skip')
            return

        logger.attr('Fleet to check', self.config.OpsiFleet_Fleet)
        self.fleet_set(self.config.OpsiFleet_Fleet)
        self.ship_info_enter(FLEET_FLAGSHIP)
        all_full_exp = True

        while 1:
            self.device.screenshot()
            level, exp = ship_info_get_level_exp(main=self)
            current_total_exp = LIST_SHIP_EXP[level - 1] + exp
            logger.info(f'Level: {level}, Exp: {exp}, Total Exp: {current_total_exp}, Target Exp: {LIST_SHIP_EXP[target_level - 1]}')
            if current_total_exp < LIST_SHIP_EXP[target_level - 1]:
                all_full_exp = False
                break
            if not self.ship_view_next():
                break

        if all_full_exp:
            logger.info(f'All ships in fleet {self.config.OpsiFleet_Fleet} are full exp, '
                        f'level {target_level} or above')
            handle_notify(
                self.config.Error_OnePushConfig,
                title=f"Alas <{self.config.config_name}> level check passed",
                content=f"<{self.config.config_name}> {self.config.task} reached level limit {target_level} or above."
            )
        self.ui_back(appear_button=EQUIPMENT_OPEN, check_button=self.is_in_map)
        self.config.OpsiCheckLeveling_LastRun = datetime.now().replace(microsecond=0)
        if all_full_exp and self.config.OpsiCheckLeveling_DelayAfterFull:
            logger.info('Delay task after all ships are full exp')
            self.config.task_delay(server_update=True)
            self.config.task_stop()
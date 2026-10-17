import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";

import { Component, onWillStart, useState } from "@odoo/owl";

export class AttendanceActionHelper extends Component {
    static template = "primetech_rh.AttendanceActionHelper";
    static props = ["noContentHelp"];
    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = useState({
            hasDemoData: false,
        });
        onWillStart(async () => {
            this.hasAttendanceRight = await user.hasGroup("primetech_rh.group_hr_attendance_manager");
            if (this.hasAttendanceRight){
                this.state.hasDemoData = await this.orm.call("hr.attendance", "has_demo_data", []);
            }
        });
    }

    loadAttendanceScenario() {
        this.actionService.doAction("primetech_rh.action_load_demo_data");
    }

    LoadTryKiosk() {
        this.actionService.doAction("primetech_rh.action_try_kiosk");
    }
};

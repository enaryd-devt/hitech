/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/views/fields/char/char_field";
import { useService } from "@web/core/utils/hooks";
import { onMounted, useEffect, useExternalListener } from "@odoo/owl";

const BARCODE_ROLL_KEY = "primetech_product_ean13_roll";

class PrimetechRollingCodeField extends CharField {
    setup() {
        super.setup();
        this.lastValue = this.props.record.data[this.props.name] || "";
        this.rollingTimer = undefined;

        useEffect(
            () => {
                const value = this.props.record.data[this.props.name] || "";
                if (value && value !== this.lastValue) {
                    this.rollToValue(value, true);
                }
                this.lastValue = value;
            },
            () => [this.props.record.data[this.props.name]]
        );

        if (this.props.name === "barcode") {
            useExternalListener(document, "click", (event) => {
                if (event.target.closest(".pt_ean13_generate_button")) {
                    window.sessionStorage.setItem(BARCODE_ROLL_KEY, "1");
                }
            });
            onMounted(() => {
                if (window.sessionStorage.getItem(BARCODE_ROLL_KEY) === "1") {
                    window.sessionStorage.removeItem(BARCODE_ROLL_KEY);
                    const value = this.props.record.data[this.props.name] || "";
                    if (value) {
                        this.rollToValue(value, true);
                    }
                }
            });
        }
    }

    rollToValue(value, force = false) {
        const input = this.input.el;
        if (!input || (!force && input.value === value)) {
            return;
        }
        window.clearInterval(this.rollingTimer);
        let step = 0;
        const steps = 8;
        input.classList.add("pt_rolling_code_active");
        this.rollingTimer = window.setInterval(() => {
            step += 1;
            if (step >= steps) {
                window.clearInterval(this.rollingTimer);
                input.value = value;
                input.classList.remove("pt_rolling_code_active");
                return;
            }
            input.value = value.replace(/\d/g, () => Math.floor(Math.random() * 10).toString());
        }, 55);
    }
}

PrimetechRollingCodeField.template = CharField.template;

registry.category("fields").add("primetech_rolling_code", {
    ...charField,
    component: PrimetechRollingCodeField,
});

class PrimetechBarcodeGeneratorField extends PrimetechRollingCodeField {
    setup() {
        super.setup();
        this.orm = useService("orm");
    }

    async onGenerateBarcode() {
        let barcode;
        if (this.props.record.resId) {
            const result = await this.orm.call(
                this.props.record.resModel,
                "action_primetech_generate_ean13",
                [[this.props.record.resId]]
            );
            barcode = result?.barcode;
        } else {
            barcode = await this.orm.call(
                this.props.record.resModel,
                "primetech_generate_ean13_value",
                []
            );
        }
        if (barcode) {
            await this.props.record.update({ [this.props.name]: barcode });
            this.rollToValue(barcode, true);
        }
    }
}

PrimetechBarcodeGeneratorField.template = "primetech_product_internal_reference.BarcodeGeneratorField";

registry.category("fields").add("primetech_barcode_generator", {
    ...charField,
    component: PrimetechBarcodeGeneratorField,
});

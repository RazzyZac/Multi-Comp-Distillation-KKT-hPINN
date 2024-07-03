import numpy as np

class CostAnalysisDist:
    
    def CAL_Column_Diameter(self, pressure, MW, XW, YD, tops_temperature, dist_flow):
        P = pressure
        f = float(1.6)
        R = 8314.0 #J/kmol * K
        density = [573,626,655] #kg/m^3 density of 3 components (butane, pentane, hexane)
        Tray_space = 0.6
        RMMtop = np.sum(np.array(MW)*np.array(YD)) #relative molecular mass
        Pv = (RMMtop * P*1e5) / (R * (tops_temperature+273.15)) #kg/m^3
        Pl = np.sum(np.array(XW)*np.array(density))
        Uv = (-0.171*Tray_space**2 + 0.27*Tray_space-0.047)*((Pl-Pv)/Pv)/2 #maximum allowable vapor velocity
        Mv = np.sum(dist_flow) / 3600 #kg/s vapor flow
        Dc = np.sqrt(4*Mv/ (3.1416*Pv*Uv))
        return Dc

    def CAL_Column_Height(self, n_stages):
        HETP = 0.5  # HETP constant [m]
        H_0 = 0.4  # Clearance [m]
        return n_stages * HETP + H_0

    def CAL_LMTD(self, tops_temperature):
        T_cool_in = 20  # Supply temperature of cooling water [oC]
        T_cool_out = 25  # Return temperature of cooling water [oC]
        delta_Tm_cnd = (((tops_temperature - T_cool_in) * (tops_temperature - T_cool_out) * (
                (tops_temperature - T_cool_in) + (tops_temperature - T_cool_out)) / 2) ** (1 / 3))
        return delta_Tm_cnd.real
        
    def CAL_HT_Condenser_Area(self, condenser_duty, tops_temperature):
        K_cnd = 500  # Heat transfer coefficient [W/m2 K]
        delta_Tm_cnd = self.CAL_LMTD(tops_temperature)
        A_cnd = -condenser_duty*4.184 / (K_cnd * delta_Tm_cnd)
        return A_cnd

    def CAL_HT_Reboiler_Area(self, reboiler_temperature, reboiler_duty):
        K_rbl = 800  # Heat transfer coefficient [W/m2*K] (800, fixed)
        T_steam = 201  # Temperature of 16 bar steam [°C] (201, fixed)
        delta_tm_rbl = T_steam - reboiler_temperature
        A_rbl = reboiler_duty*4.184 / (K_rbl * delta_tm_rbl)
        return A_rbl

    def CAL_OperatingCost(self, reboiler_duty, condenser_duty):
        M = 18  # Molar weight of water [g/mol] (18, fixed)
        c_steam = 18  # Steam price [€/ton] (18, fixed)
        c_cw = 0.026  # Cooling water price [€/ton] (0.006, fixed)
        delta_hv = 34794  # Molar heat of condensation of 16 bar steam [J/mol] (34794, fixed)
        c_p = 4.2  # Heat capacity of water [kJ/(kg*K)] (4.2, fixed)
        T_cool_in = 20  # Supply cooling water temperature [°C] (30, fixed)
        T_cool_out = 25  # Return cooling water temperature [°C] (40, fixed)
        reboiler_duty = reboiler_duty*4.184 #J / s
        condenser_duty = condenser_duty*4.184 #J / s
        C_op_rbl = reboiler_duty * M * c_steam / 907184.74 * 3600 / delta_hv  # €/h
        C_op_cnd = -condenser_duty * c_cw / 907184.74 * 3600 / (c_p * (T_cool_out - T_cool_in))  # €/h     
        C_op = C_op_rbl + C_op_cnd
        return C_op_rbl, C_op_cnd

    def CAL_Annual_OperatingCost(self, reboiler_duty, condenser_duty):
        t_a = 8400
        C_op_rbl,C_op_cnd = self.CAL_OperatingCost(reboiler_duty, condenser_duty)
        Rbl_cost = C_op_rbl*t_a
        Cnd_cost = C_op_cnd*t_a
        return Rbl_cost,Cnd_cost
        
    def CAL_InvestmentCost(self, pressure, n_stages, condenser_duty, reboiler_temperature, reboiler_duty,
                               tops_temperature, MW, XW, YD, dist_flow):

            # Define in Column Specifications
            L = self.CAL_Column_Height(n_stages)  # Column length [m]
            if tops_temperature is not None and dist_flow is not None:
                D = self.CAL_Column_Diameter(pressure, MW, XW, YD, tops_temperature, dist_flow)  # Column diameter [m]
            else:
                D=1
            if condenser_duty is not None and tops_temperature is not None:
                A_cnd = self.CAL_HT_Condenser_Area(condenser_duty, tops_temperature)  # Heat transfer area of condenser [m2]
            else:
                A_cnd = 1
            if reboiler_duty is not None and reboiler_temperature is not None:
                A_rbl = self.CAL_HT_Reboiler_Area(reboiler_temperature, reboiler_duty)  # Heat transfer area of reboiler [m2]
            else:
                A_rbl = 1
            # Predefined values.
            F_m = 1  # Correction factor for column shell material (1.0, fixed)
            F_p = 1  # Correction factor for column pressure (1.0, fixed)
            F_int_m = 0  # Correction factor for internals material [-] (0.0, fixed)
            F_int_t = 0  # Correction factor for tray type [-] (0.0, fixed)
            F_int_s = 1.4  # Correction factor for tray spacing [-] (1.4, fixed)
            F_htx_d = 0.8  # Correction factor for design type: fixed-tube sheet [-] (0.8, fixed)
            F_htx_p = 0  # Correction factor for pressure [-] (0.0, fixed)
            F_htx_m = 1  # Correction factor for material [-] (1.0, fixed)
            M_S = 1638.2  # Marshall & Swift equipment index 2018 (1638.2, fixed)
            F_c = F_m + F_p
            F_int_c = F_int_s + F_int_t + F_int_m
            F_cnd_c = (F_htx_d + F_htx_p) * F_htx_m
            F_rbl_c = (F_htx_d + F_htx_p) * F_htx_m
            C_col = 0.9 * (M_S / 280) * 937.64 * D ** 1.066 * L ** 0.802 * F_c
            C_int = 0.9 * (M_S / 280) * 97.24 * D ** 1.55 * L * F_int_c
            C_cnd = 0.9 * (M_S / 280) * 474.67 * A_cnd ** 0.65 * F_cnd_c
            C_rbl = 0.9 * (M_S / 280) * 474.67 * A_rbl ** 0.65 * F_rbl_c
            C_eqp = (C_col + C_int + C_cnd + C_rbl)
            F_cap = 1  # Capital charge factor (1, fixed)
            F_L = 5  # Lang factor (5, fixed)
            C_inv = F_L * C_eqp
            InvestmentCost = F_cap * C_inv
            return InvestmentCost

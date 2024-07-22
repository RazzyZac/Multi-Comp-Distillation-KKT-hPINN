import os
import win32com.client as win32
from data.cost_analysis_dist import CostAnalysisDist
import numpy as np

class StreamDataGeneratorAspenDIST:
    def __init__(self, system):
        self.aspen = system
        self.all_streams = None
        self.all_in_streams = None
        self.all_out_streams = None
        self.all_components = None
        self.all_blocks = None
        self.all_paths = []
        self.stream_dict = {}
        self.ATMOS_TEMP = 25
        self.ATMOS_PRES = 1.033

    def _get_flow_data(self):
        self.stream_dict = {}
        for stream in self.all_streams:
            self.stream_dict[stream] = {}
            self.stream_dict[stream]["MOLEFLOW"] = {}
            
            """for component in self.all_components: 
                self.stream_dict[stream]["MOLEFLOW"][component] = 0"""
        #same code as above for loop, but going through the blocks.
        for block in self.all_blocks:
            self.stream_dict[block] = {}
            self.stream_dict[block]["COND-DUTY"] = 0
            self.stream_dict[block]["REB-DUTY"] = 0
            self.stream_dict[block]["FEED_TRAY"] = 0
            self.stream_dict[block]["DIST_RATE"] = 0
            self.stream_dict[block]["REFLUX_RATIO"] = 0

        for stream in self.all_streams:
            # Mole Flow data
            for component in self.all_components:
                print(f'retrieving Stream: {stream}, Component: {component}')
                component_moleflow_path = "\Data\Streams\{}\Output\MOLEFLOW\MIXED\{}".format(stream, component)
                component_moleflow_value = self.aspen.Tree.FindNode(component_moleflow_path).Value
                if component_moleflow_value is not None:
                    self.stream_dict[stream]["MOLEFLOW"][component] = component_moleflow_value
                else:
                    self.stream_dict[stream]["MOLEFLOW"][component] = 'Returned None'

        for block in self.all_blocks:
            # Reboiler heat duty
            rebduty_path = "\Data\Blocks\{}\Output\REB_DUTY".format(block)
            rebduty_value = self.aspen.Tree.FindNode(rebduty_path).Value
            if rebduty_value is not None:
                self.stream_dict[block]["REB-DUTY"] = rebduty_value
            else:
                self.stream_dict[block]["REB-DUTY"] = 'Returned None' 

            # Condensor heat duty
            cond_duty_path = "\Data\Blocks\{}\Output\COND_DUTY".format(block)
            cond_duty_value = self.aspen.Tree.FindNode(cond_duty_path).Value
            if cond_duty_value is not None:
                self.stream_dict[block]["COND-DUTY"] = cond_duty_value
            else:
                self.stream_dict[block]["COND-DUTY"] = 'Returned None'  

            #distillate rate
            dist_rate_path = "\\Data\\Blocks\\{}\\Input\\BASIS_D".format(block)
            dist_rate_value = self.aspen.Tree.FindNode(dist_rate_path).Value
            if dist_rate_value is not None:
                self.stream_dict[block]["DIST_RATE"] = dist_rate_value
            else:
                self.stream_dict[block]["DIST_RATE"] = 'Returned None' 

            #reflux ratio
            ref_rat_path = "\\Data\\Blocks\\{}\\Input\\BASIS_RR".format(block)
            ref_rat_value = self.aspen.Tree.FindNode(ref_rat_path).Value
            if ref_rat_value is not None:
                self.stream_dict[block]["REFLUX_RATIO"] = ref_rat_value
            else:
                self.stream_dict[block]["REFLUX_RATIO"] = 'Returned None'
            #investment cost
            pressure = self.aspen.Tree.FindNode(r"\Data\Blocks\B1\Input\PRES1").Value
            n_stages = self.aspen.Tree.FindNode("\Data\Blocks\B1\Input\\NSTAGE").Value
            cond_duty = self.aspen.Tree.FindNode(r"\Data\Blocks\B1\Output\COND_DUTY").Value
            reb_duty = self.aspen.Tree.FindNode(r"\Data\Blocks\B1\Output\REB_DUTY").Value
            reb_temp = self.aspen.Tree.FindNode(r"\Data\Blocks\B1\Output\REB_TOUT").Value
            top_temp = self.aspen.Tree.FindNode(r"\Data\Blocks\B1\Output\TOP_TEMP").Value
            dist_flow = []
            MW = [58.120,72.15,86.18] #molecular weights for each component
            YD = [] #mole fraction composition of distillate stream
            XW = [] #mole fraction composition of bottom stream
            comps = ["N-BUTANE", "N-PENTAN", "N-HEXANE"]
            for i in comps:
                YD.append(self.aspen.Tree.FindNode("\Data\Streams\DIST\Output\MOLEFRAC\MIXED\{}".format(i)).Value)
                XW.append(self.aspen.Tree.FindNode("\Data\Streams\BOTT\Output\MOLEFRAC\MIXED\\{}".format(i)).Value)
                dist_flow.append(self.aspen.Tree.FindNode("\Data\Streams\DIST\Output\MASSFLOW\MIXED\\{}".format(i)).Value)
            cost_analysis = CostAnalysisDist()
            InvestmentCost = cost_analysis.CAL_InvestmentCost(pressure=pressure,n_stages=n_stages,condenser_duty=cond_duty,
                                                      reboiler_temperature=reb_temp,reboiler_duty=reb_duty,tops_temperature=top_temp,
                                                              MW=MW,XW=XW,YD=YD,dist_flow=dist_flow)
            Rbl_cost,Cnd_cost = cost_analysis.CAL_Annual_OperatingCost(reboiler_duty=reb_duty,condenser_duty=cond_duty)
            if type(InvestmentCost) is not type(np.complex128()):
                self.stream_dict[block]["Investment Cost"] = InvestmentCost
            else:
                self.stream_dict[block]["Investment Cost"] = "Returned None"
            self.stream_dict[block]["Operating Cost Reboiler"] = Rbl_cost
            self.stream_dict[block]["Operating Cost Condenser"] = Cnd_cost

            #Top temperature
            top_temp_path =  "\\Data\\Blocks\\B1\\Output\\TOP_TEMP"
            top_temp_value = self.aspen.Tree.FindNode(top_temp_path).Value
            if top_temp_value is not None:
                self.stream_dict[block]["TOP_TEMP"] = top_temp_value
            else:
                self.stream_dict[block]["TOP_TEMP"] = 'Returned None'

            #Reboiler Temperature
            reb_temp_path = "\\Data\\Blocks\\B1\\Output\\REB_TOUT"
            reb_temp_value = self.aspen.Tree.FindNode(reb_temp_path).Value
            if reb_temp_value is not None:
                self.stream_dict[block]["REB_TEMP"] = reb_temp_value
            else:
                self.stream_dict[block]["REB_TEMP"] = 'Returned None'
                
            print(self.stream_dict)

    def _get_stream_information(self, tree_path):
        print(self.aspen.Tree.FindNode(tree_path).Value)

    def get(self, path):
        self._get_stream_information(tree_path=path)

    def generate(self,
                 all_streams_list,
                 all_in_streams_list,
                 all_out_streams_list,
                 all_components,
                 all_blocks):
        self.all_streams = all_streams_list
        self.all_in_streams = all_in_streams_list
        self.all_out_streams = all_out_streams_list
        self.all_components = all_components
        self.all_blocks = all_blocks
        self._get_flow_data()
        return self.stream_dict

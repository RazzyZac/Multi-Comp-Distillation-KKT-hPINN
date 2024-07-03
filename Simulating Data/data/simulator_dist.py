import json
import numpy as np
from scipy.stats.qmc import Sobol
from tqdm import tqdm

class StreamDataSimulatorAspenDIST:
    def __init__(self,
                 engine,
                 generator,
                 attributes_dict,
                 num_points,
                 start_point):
        self.engine = engine
        self.attributes = attributes_dict
        self.generator = generator
        self.num_points = num_points
        self.start_point = start_point
        self.all_streams = None
        self.all_in_streams = None
        self.all_out_streams = None
        self.all_components = None
        self.save_path = None
        self.all_blocks = None

    def _create_variable_ranges(self):
        self.variable_ranges = []
        print(self.attributes.keys())
        self.feedflow = 1000
        for key in self.attributes.keys():
            if key == "FEED":  
                xa_range_s01 = tuple(self.attributes[key]["xa"])
                self.variable_ranges.append(xa_range_s01)
                
                xb_range = tuple(self.attributes[key]["xb"])
                self.variable_ranges.append(xb_range)

                n_tray = tuple(self.attributes[key]["#-trays"])
                self.variable_ranges.append(n_tray)

                flowrate = tuple(self.attributes[key]["Flowrate"])
                self.variable_ranges.append(flowrate)

                dist_rate = tuple(self.attributes[key]["Dist rate"])
                self.variable_ranges.append(dist_rate)

                reflux_ratio = tuple(self.attributes[key]["Reflux Ratio"])
                self.variable_ranges.append(reflux_ratio)

                pressure = tuple(self.attributes[key]["Pressure"])
                self.variable_ranges.append(pressure)

        self.n_features = len(self.variable_ranges)

        print(f'variable_ranges: {self.variable_ranges}')
        print(f'n_features: {len(self.variable_ranges)}')

    def _quasi_monte_carlo(self):
        # Generate a Sobol sequence for n_variables
        num_components = 3
        num_dependent_input = 2 #inputs that depend on the other inputs, such as flow of C and feed tray
        m = int(-(-np.log2(self.start_point + self.num_points)//1)) #rounding up with floor divide
        sampler = Sobol(self.n_features+num_dependent_input-1,scramble=True,seed=42) #subtracting 1 because flow of C doesn't use sobol points
        sobol_points = np.array(sampler.random_base2(m+1))
        print('a')
        print(sobol_points.shape)
        filtered_sobol_points = sobol_points[self.start_point: self.start_point + self.num_points]
        print('b')
        print(filtered_sobol_points.shape)
        # Initialize an empty array to store the samples
        self.samples = np.zeros((self.num_points, self.n_features+num_dependent_input))
        print(self.samples.shape)
        print('c')
        flow_samples_temp = np.zeros((self.num_points,num_components))

        # Scale and shift the Sobol points to match the specified variable ranges
        xa = self.variable_ranges[0][0] + filtered_sobol_points[:, 0] * (
                    self.variable_ranges[0][1] - self.variable_ranges[0][0])
        xb = self.variable_ranges[1][0] + filtered_sobol_points[:, 1] * (
            self.variable_ranges[1][1] - self.variable_ranges[1][0])
        flow_samples_temp[:,0] = xa
        flow_samples_temp[:,1] = (1-xa)*filtered_sobol_points[:,1]
        flow_samples_temp[:,2] = 1 - xa - flow_samples_temp[:,1]
        for row in flow_samples_temp:
            np.random.shuffle(row)

        self.samples[:,0] = flow_samples_temp[:,0]
        self.samples[:,1] = flow_samples_temp[:,1]
        self.samples[:,2] = flow_samples_temp[:,2]

        num_trays = self.variable_ranges[2][0] + filtered_sobol_points[:,2] * (
            self.variable_ranges[2][1] - self.variable_ranges[2][0])
        num_trays = np.round(num_trays).astype(int)
        
        feed_tray =  2 + filtered_sobol_points[:,3] * .5*( 
            num_trays - 2) #feed tray needs to be between the second spot and half the nth spot (n is the number of trays)
        feed_tray = np.round(feed_tray).astype(int)
        self.samples[:,3] = num_trays
        self.samples[:,4] = feed_tray

        flowrate = self.variable_ranges[3][0] + filtered_sobol_points[:,3] * (
            self.variable_ranges[3][1] - self.variable_ranges[3][0])
        self.samples[:,5] = flowrate

        dist_rate = self.variable_ranges[4][0] + filtered_sobol_points[:,4] * (
            self.variable_ranges[4][1] - self.variable_ranges[4][0])
        self.samples[:,6] = dist_rate
        
        reflux_ratio = self.variable_ranges[5][0] + filtered_sobol_points[:,5] * (
            self.variable_ranges[5][1] - self.variable_ranges[5][0])
        self.samples[:,7] = reflux_ratio

        pressure = self.variable_ranges[6][0] + filtered_sobol_points[:,6] * (
            self.variable_ranges[5][1] - self.variable_ranges[5][0])
        self.samples[:,8] = pressure
        print(f'samples: {self.samples}')

        return self.samples

    def _configure_simulation(self):
        self.simulation_collector = {
            "1": {},
        }
        self._create_variable_ranges()
        self._quasi_monte_carlo()

    def _run_engine(self):
        self.engine.Reinit()
        self.engine.Engine.Run2()

    def _run_simulation(self):
        self._configure_simulation()
        i = 1
        
        FLOW_A_path = "\\Data\\Streams\\FEED\\Input\\FLOW\\MIXED\\N-BUTANE"
        FLOW_B_path = "\\Data\\Streams\\FEED\\Input\\FLOW\\MIXED\\N-PENTAN"
        FLOW_C_path = "\\Data\\Streams\\FEED\\Input\\FLOW\\MIXED\\N-HEXANE"
        num_tray_path = "\\Data\\Blocks\\B1\\Input\\NSTAGE"
        feed_tray_path = "\\Data\\Blocks\\B1\\Input\\FEED_STAGE\\FEED"
        dist_rate_path = "\\Data\\Blocks\\B1\\Input\\BASIS_D"
        reflux_ratio_path = "\\Data\\Blocks\\B1\\Input\\BASIS_RR"
        pressure_block_path = "\\Data\\Blocks\\B1\\Input\\PRES1"
        pressure_flow_path = "\\Data\\Streams\\FEED\\Input\\PRES\\MIXED"

        for sample in tqdm(self.samples):
            #  FEED
            self.engine.Tree.FindNode(FLOW_A_path).Value = sample[0]*sample[5]  # Flow A
            self.engine.Tree.FindNode(FLOW_B_path).Value = sample[1]*sample[5]  # Flow B
            self.engine.Tree.FindNode(FLOW_C_path).Value = sample[2]*sample[5]  #Flow C
            self.engine.Tree.FindNode(num_tray_path).Value = int(sample[3])  #number of trays
            self.engine.Tree.FindNode(feed_tray_path).Value = int(sample[4])  #feed tray location
            self.engine.Tree.FindNode(dist_rate_path).Value = sample[6]*(sample[5]) #distillate rate is .25-.75 times the total flow rate
            self.engine.Tree.FindNode(reflux_ratio_path).Value = sample[7]
            self.engine.Tree.FindNode(pressure_block_path).Value = sample[8]
            self.engine.Tree.FindNode(pressure_flow_path).Value = sample[8]

            print('\ngenerating for  ...')
            print(f'{self.engine.Tree.FindNode(FLOW_A_path).Value} \n'
                  f'{self.engine.Tree.FindNode(FLOW_B_path).Value} \n'
                  f'{self.engine.Tree.FindNode(FLOW_C_path).Value} \n'
                  f'{self.engine.Tree.FindNode(num_tray_path).Value} \n'
                  f'{self.engine.Tree.FindNode(feed_tray_path).Value} \n'
                  f'{self.engine.Tree.FindNode(dist_rate_path).Value} \n'
                  f'{self.engine.Tree.FindNode(reflux_ratio_path).Value} \n'
                  f'{self.engine.Tree.FindNode(pressure_block_path).Value} \n')

            #  Run the system and saving the results
            self._run_engine()
            self.simulation_result = self.generator.generate(all_streams_list=self.all_streams,
                                                             all_in_streams_list=self.all_in_streams,
                                                             all_out_streams_list=self.all_out_streams,
                                                             all_components=self.all_components,
                                                             all_blocks = self.all_blocks)
            self.simulation_collector[str(i)] = self.simulation_result
            i += 1
            # Save the dictionary to a JSON file
            with open(self.save_path, 'w') as json_file:
                json.dump(self.simulation_collector, json_file, indent=4)

    def save_results(self, save_path):
        self.save_path = save_path

        # Save the dictionary to a JSON file
        with open(self.save_path, 'w') as json_file:
            json.dump(self.simulation_collector, json_file, indent=4)

    def simulate(self,
                 all_streams_list,
                 all_in_streams_list,
                 all_out_streams_list,
                 all_components,
                 all_blocks,
                 save_path):
        self.all_streams = all_streams_list
        self.all_in_streams = all_in_streams_list
        self.all_out_streams = all_out_streams_list
        self.all_components = all_components
        self.all_blocks = all_blocks
        self.save_path = save_path
        self._run_simulation()
        return self.simulation_collector
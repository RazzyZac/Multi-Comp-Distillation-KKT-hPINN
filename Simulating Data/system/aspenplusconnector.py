import os
import win32com.client as win32


class ASPENConnector:
    def __init__(self, base_path):
        self.base_path = base_path
        self.app_name = "Apwn.Document"

    def _dispatch(self):
        self.aspen = win32.Dispatch(self.app_name)

        # win32.Dispatch('Apwn.Document.37.0') is ASPEN PLUS V11.0

    def __open_system(self):
        self.aspen.InitFromArchive2(self.base_path)
        self.aspen.Visible = 1
        self.aspen.SuppressDialogs = 1
        # self.aspen.Reinit()
        # self.aspen.Engine.Run2()

    def connect(self):
        self._dispatch()
        print("Connected to ASPEN...")
        self.__open_system()
        print("ASPEN File Loaded...")

    def close(self):
        self.aspen.Close()
        print("Aspen Closed")


"""
fix_winterkill.py: runtime patches for PCSE 6.0.12. Import once, before building any
PCSE Engine.

1. Wofost_winterkill. The crop wrapper bundled with PCSE 6.0.x has fallen out of step
   with wofost72.py. It declares PGASS and PMRES as crop-level rate variables that the
   assimilation and respiration modules now own, never publishes the REALLOC_LV/ST/SO
   rates that the current leaf, stem and storage-organ modules read, computes GASS as
   PGASS * TRA / TRAMX (a division by zero when TRAMX is 0), and its crop_finish handler
   does not accept the finish_type keyword the signal sends. The patch realigns all four
   with wofost72.py.
2. NASA POWER end date. PCSE requests data up to today, but the POWER feed lags by about
   two weeks and the API then returns HTTP 422. Requests are capped at
   NASA_END_BUFFER_DAYS before today.
3. NASA POWER rainfall range. PCSE rejects RAIN above 25 cm/day, so one spurious extreme
   day in a multi-decade POWER record drops the whole cell. The upper bound is raised to
   100 cm/day. A single extreme rain day only affects the soil water balance, which does
   not drive frost kill.
"""
from pcse.crop import wofost_winterkill as _wk
from pcse.base import RatesTemplate
from pcse.traitlets import Float
from pcse.decorators import prepare_rates

class _RateVariables(RatesTemplate):
    GASS = Float(-99.); MRES = Float(-99.); ASRC = Float(-99.)
    DMI = Float(-99.); ADMI = Float(-99.)
    REALLOC_LV = Float(0.); REALLOC_ST = Float(0.); REALLOC_SO = Float(0.)
_wk.Wofost_winterkill.RateVariables = _RateVariables

def _initialize(self, day, kiosk, parvalues):
    self.params = self.Parameters(parvalues)
    self.rates  = self.RateVariables(kiosk, publish=["DMI","ADMI","REALLOC_LV","REALLOC_ST","REALLOC_SO"])
    self.kiosk = kiosk
    self.pheno = _wk.Phenology(day, kiosk, parvalues)
    self.part  = _wk.Partitioning(day, kiosk, parvalues)
    self.assim = _wk.Assimilation(day, kiosk, parvalues)
    self.mres  = _wk.MaintenanceRespiration(day, kiosk, parvalues)
    self.evtra = _wk.Evapotranspiration(day, kiosk, parvalues)
    self.crowntemp = _wk.CrownTemperature(day, kiosk, parvalues)
    self.frostol = _wk.FROSTOL(day, kiosk, parvalues)
    self.ro_dynamics = _wk.Root_Dynamics(day, kiosk, parvalues)
    self.st_dynamics = _wk.Stem_Dynamics(day, kiosk, parvalues)
    self.so_dynamics = _wk.Storage_Organ_Dynamics(day, kiosk, parvalues)
    self.lv_dynamics = _wk.Leaf_Dynamics(day, kiosk, parvalues)
    TAGP = self.kiosk["TWLV"] + self.kiosk["TWST"] + self.kiosk["TWSO"]
    self.states = self.StateVariables(kiosk, publish=["TAGP","GASST","MREST","HI"],
                                      TAGP=TAGP, GASST=0.0, MREST=0.0, CTRAT=0.0, HI=0.0,
                                      DOF=None, FINISH_TYPE=None)
    checksum = parvalues["TDWI"] - self.states.TAGP - self.kiosk["TWRT"]
    if abs(checksum) > 0.0001:
        raise _wk.exc.PartitioningError("Error in partitioning of initial biomass (TDWI)!")
    self._connect_signal(self._on_CROP_FINISH, signal=_wk.signals.crop_finish)
_wk.Wofost_winterkill.initialize = _initialize

@prepare_rates
def _calc_rates(self, day, drv):
    params = self.params; rates = self.rates
    self.pheno.calc_rates(day, drv)
    if self.pheno.get_variable("STAGE") == "emerging":
        return
    PGASS = self.assim(day, drv)
    self.evtra(day, drv)
    rates.GASS = PGASS * self.kiosk["RFTRA"]   # matches wofost72.py; avoids TRAMX=0 division
    PMRES = self.mres(day, drv)
    rates.MRES = min(rates.GASS, PMRES)
    rates.ASRC = rates.GASS - rates.MRES
    pf = self.part.calc_rates(day, drv)
    CVF = 1./((pf.FL/params.CVL + pf.FS/params.CVS + pf.FO/params.CVO) * (1.-pf.FR) + pf.FR/params.CVR)
    rates.DMI = CVF * rates.ASRC
    self._check_carbon_balance(day, rates.DMI, rates.GASS, rates.MRES, CVF, pf)
    rates.REALLOC_LV = 0.0; rates.REALLOC_ST = 0.0; rates.REALLOC_SO = 0.0
    self.crowntemp(day, drv)
    self.frostol.calc_rates(day, drv)
    self.ro_dynamics.calc_rates(day, drv)
    rates.ADMI = (1. - pf.FR) * rates.DMI
    self.st_dynamics.calc_rates(day, drv)
    self.so_dynamics.calc_rates(day, drv)
    self.lv_dynamics.calc_rates(day, drv)
_wk.Wofost_winterkill.calc_rates = _calc_rates
print("[fix_winterkill] patch applied (PGASS/PMRES locals + REALLOC published)")

def _on_CROP_FINISH(self, day, finish_type=None):
    self._for_finalize["DOF"] = day
    self._for_finalize["FINISH_TYPE"] = finish_type
_wk.Wofost_winterkill._on_CROP_FINISH = _on_CROP_FINISH
print("[fix_winterkill] _on_CROP_FINISH signature aligned")

# ===========================================================================
# NASA POWER end-date fix (independent of the winterkill fix above)
# pcse's NASAPowerWeatherDataProvider requests data up to dt.date.today(), but the
# NASA POWER daily feed lags ~2 weeks, so the server returns HTTP 422. Cap the end
# date to ~1 month ago (ample for any past winter, including 2025/26). If a 422
# persists after this, raise the buffer (radiation can lag further).
import datetime as _dt
import requests as _requests
from pcse.input import nasapower as _np

NASA_END_BUFFER_DAYS = 30

def _query_NASAPower_server_capped(self, latitude, longitude):
    start_date = _dt.date(1983, 7, 1)
    end_date   = _dt.date.today() - _dt.timedelta(days=NASA_END_BUFFER_DAYS)
    server  = "https://power.larc.nasa.gov/api/temporal/daily/point"
    payload = {"request": "execute", "parameters": ",".join(self.power_variables),
               "latitude": latitude, "longitude": longitude,
               "start": start_date.strftime("%Y%m%d"), "end": end_date.strftime("%Y%m%d"),
               "community": "AG", "format": "JSON", "user": "wurblacksea"}
    req = _requests.get(server, params=payload)
    if req.status_code != self.HTTP_OK:
        raise _np.PCSEError("Failed retrieving POWER data, server returned HTTP "
                            "code: %i on following URL %s" % (req.status_code, req.url))
    return req.json()

_np.NASAPowerWeatherDataProvider._query_NASAPower_server = _query_NASAPower_server_capped
print("[fix_winterkill] NASA POWER end-date capped to today-%dd" % NASA_END_BUFFER_DAYS)

# ===========================================================================
# NASA POWER RAIN-range fix (independent of the fixes above)
# pcse's WeatherDataContainer hard-caps RAIN at (0, 25) cm/day. NASA POWER (MERRA-2)
# occasionally reports a single spurious/extreme day above 250 mm somewhere in a cell's
# multi-decade record, which trips this range check and makes the ENTIRE provider fetch
# raise -- so that cell is silently dropped from the grid. This hit ~17 production-weighted
# cells in the Volga / lower-Don belt (lon ~45-51E). Loosen the upper bound so those cells
# run; a lone extreme-rain day only touches the soil water balance, which is immaterial for
# a frost-kill signal. Must run before any provider/Engine is built (this module already is).
from pcse.base import WeatherDataContainer as _WDC
_WDC.ranges["RAIN"] = (0.0, 100.0)
print("[fix_winterkill] RAIN range loosened to (0, 100) cm/day for NASA POWER outliers")

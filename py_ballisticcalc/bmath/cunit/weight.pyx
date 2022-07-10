WeightGrain = 70
WeightOunce = 71
WeightGram = 72
WeightPound = 73
WeightKilogram = 74
WeightNewton = 75


cdef class Weight:
    cdef float _value
    cdef int _default_units
    cdef __name__

    def __init__(self, value: float, units: int):
        self.__name__ = 'Weight'
        self._value = self.to_default(value, units)
        self._default_units = units

    cdef float to_default(self, value: float, units: int):
        if units == WeightGrain:
            return value
        elif units == WeightGram:
            return value * 15.4323584
        elif units == WeightKilogram:
            return value * 15432.3584
        elif units == WeightNewton:
            return value * 151339.73750336
        elif units == WeightPound:
            return value / 0.000142857143
        elif units == WeightOunce:
            return value * 437.5
        else:
            raise KeyError(f'{self.__name__}: unit {units} is not supported')

    cdef float from_default(self, value: float, units: int):
        if units == WeightGrain:
            return value
        elif units == WeightGram:
            return value / 15.4323584
        elif units == WeightKilogram:
            return value / 15432.3584
        elif units == WeightNewton:
            return value / 151339.73750336
        elif units == WeightPound:
            return value * 0.000142857143
        elif units == WeightOunce:
            return value / 437.5
        else:
            raise KeyError(f'KeyError: {self.__name__}: unit {units} is not supported')

    cpdef float value(self, units: int):
        return self.from_default(self._value, units)

    cpdef Weight convert(self, units: int):
        cdef float value = self.get_in(units)
        return Weight(value, units)

    cpdef float get_in(self, units: int):
        return self.from_default(self._value, units)

    def __str__(self):
        return self.string()

    cdef string(self):
        cdef name
        cdef int accuracy
        cdef int default = self._default_units
        cdef float v = self.from_default(self._value, default)
        if default == WeightGrain:
            name = 'gr'
            accuracy = 0
        elif default == WeightGram:
            name = 'g'
            accuracy = 1
        elif default == WeightKilogram:
            name = 'kg'
            accuracy = 3
        elif default == WeightNewton:
            name = 'N'
            accuracy = 3
        elif default == WeightPound:
            name = 'lb'
            accuracy = 3
        elif default == WeightOunce:
            name = 'oz'
            accuracy = 1
        else:
            name = '?'
            accuracy = 6

        return f'{round(v, accuracy)} {name}'

    cpdef int units(self):
        return self._default_units

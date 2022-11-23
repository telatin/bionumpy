from npstructures import RaggedArray
from npstructures.mixin import NPSArray
from typing import Tuple
from .encodings.base_encoding import BaseEncoding, Encoding, NumericEncoding
from .encodings.identity_encoding import IdentityEncoding
from .util import is_subclass_or_instance
import numpy as np


class EncodingException(Exception):
    pass


class IncompatibleEncodingsException(Exception):
    pass


class EncodedRaggedArray(RaggedArray):
    """ Class to represnt EnocedArray with different row lengths """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assert isinstance(self._data, EncodedArray)

    def __repr__(self) -> str:
        if self.size>1000:
            rows = [str(row) for row in self[:5]]
        else:
            rows = [f"{row}" for row in self]
        encoding_info = f", {self.encoding}" if not self.encoding.is_base_encoding()  else ""
        indent = " "*len("encoded_ragged_array([")
        quotes = "'" if self.encoding.is_one_to_one_encoding() else ""
        lines = [f"{indent}{quotes}{row}{quotes}," for row in rows]
        lines[0] = lines[0].replace(indent, "encoded_ragged_array([")
        if self.size > 1000:
            lines.insert(-1, "...")
        lines[-1] = lines[-1][:-1] + "]" + encoding_info + ")"
        return "\n".join(lines)

    @property
    def encoding(self):
        """Make the encoding of the underlying data avaible"""
        return self._data.encoding

    def raw(self):
        return RaggedArray(self._data.raw(), self.shape)

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        """ Convert any data to `EncodedArray` before calling the `ufunc` on them """
        assert isinstance(self._data, EncodedArray), self._data
        inputs = [as_encoded_array(i, self._data.encoding).raw() for i in inputs]
        kwargs = {key: as_encoded_array(val, self._data.encoding).raw() for key, val in kwargs.items()}

        ret = super().__array_ufunc__(ufunc, method, *inputs, **kwargs)
        if isinstance(ret._data, EncodedArray):
            return EncodedRaggedArray(ret._data, ret.shape)
        return ret


def get_NPSArray(array):
    return array.view(NPSArray)


class EncodedArray(np.lib.mixins.NDArrayOperatorsMixin):
    """ 
    Class for data that could be written as characters, but is represented numpy arrays
    """

    encoding = None

    def __init__(self, data: np.ndarray, encoding: Encoding = BaseEncoding):
        """Create an encoded array form raw data and encoding.

        This should seldom be used directly. Only when you for some reason 
        have encoded data that is not yet represented as an `EncodedArray`.

        Use `as_encoded_array` to create encoded arrays from `str` objects

        Parameters
        ----------
        data : np.ndarray
            Raw encoded data
        encoding : Encoding
            The encoding that the data already has

        """
        if isinstance(data, EncodedArray):
            assert data.encoding == encoding
            data = data.data
        self.encoding = encoding
        dtype = None if hasattr(data, "dtype") else np.uint8
        #self.data = np.asarray(data, dtype=dtype).view(NPSArray)
        self.data = np.asarray(data, dtype=dtype)
        self.data = get_NPSArray(self.data)
        #assert isinstance(self.data, np.ndarray)

    def __len__(self) -> int:
        return len(self.data)

    def raw(self) -> np.ndarray:
        return self.data.view(np.ndarray)

    def to_string(self) -> str:
        return "".join([chr(c) for c in self.encoding.decode(self.data)])

    def reshape(self, *args, **kwargs) -> "EncodedArray":
        return self.__class__(self.data.reshape(*args, **kwargs), self.encoding)

    @property
    def size(self) -> int:
        return self.data.size

    @property
    def shape(self) -> Tuple[int]:
        return self.data.shape

    @property
    def strides(self) -> Tuple[int]:
        return self.data.strides

    @property
    def dtype(self) -> np.dtype:
        return self.data.dtype

    def __repr__(self) -> str:
        quotes = "'" if self.encoding.is_one_to_one_encoding() else ""
        if self.encoding.is_base_encoding():
            return f"encoded_array({quotes}{str(self)}{quotes})"
        return f"encoded_array({quotes}{str(self)}{quotes}, {self.encoding})"

    def __str__(self) -> str:
        """Return the data decoded into ASCII string

        Only return the first 20 chars and/or first 20 rows

        Returns
        -------
        str

        """
        if not self.encoding.is_one_to_one_encoding():
            # not possible to decode, get string
            n_dims = len(self.data.shape)
            assert n_dims in [0, 1, 2], "Unsupported number of dimensions for data"

            data_to_show = self.data
            if n_dims == 0:
                return self.encoding.to_string(self.data)
            elif n_dims == 1:
                data_to_show = data_to_show[0:20]
            elif n_dims == 2:
                # show first columns and rows
                #raise NotImplemented("Str for n_dims=2 not implemented")
                return self.encoding.to_string(self.data)[0:40] + "..."
                # data_to_show = None
            text = "[" + ", ".join(self.encoding.to_string(e) for e in data_to_show) + "]"
            return text

        else:
            text = self.encoding.decode(self.data)

            if len(self.data.shape) == 0:
                return chr(int(text))
            if len(self.data.shape) == 1:
                return "".join(chr(n) for n in text[:20]) + "..."*(len(text)>20)

            a = np.array([str(self.__class__(seq, self.encoding))
                          for seq in self.data.reshape(-1, self.data.shape[-1])]
                         ).reshape(self.data.shape[:-1])[:20]
            return str(a)


    def __getitem__(self, idx) -> "EncodedArray":
        """Delegate the indexing to the underlying numpy array

        Always return EncodedArray object. Even for scalars

        Parameters
        ----------
        idx :
            Any index understood by numpy

        Returns
        -------
        "EncodedArray"

        """
        new_data = self.data.__getitem__(idx)
        if isinstance(new_data, RaggedArray):
            return EncodedRaggedArray(EncodedArray(new_data.ravel(), self.encoding),
                                      new_data.shape)
        return self.__class__(new_data, self.encoding)

    def __setitem__(self, idx, value: "EncodedArray"):
        """ Set the item on the underlying numpy array

        Converts any string values to EncodedArray first

        Parameters
        ----------
        idx : 3
            Any index understood by numpy
        value : "EncodedArray"
            Anything that can be encoded to EncodedArray

        """
        assert isinstance(value, str) or isinstance(value, EncodedArray)

        if isinstance(value, str):
            value = encode_string(value, self.encoding)

        self.data.__setitem__(idx, value.data)

    def __iter__(self):
        return (self.__class__(element, self.encoding) for element in self.data)

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        """Handle numpy ufuncs called on EnocedArray objects

        Only support euqality checks for now. Numeric operations must be performed
        directly on the underlying data.
        """
        #if method == "__call__" and ufunc in (np.equal, np.not_equal):
        if method == "__call__" and ufunc.__name__ in ("equal", "not_equal"):
            return ufunc(*(as_encoded_array(a, self.encoding).raw() for a in inputs))
        return NotImplemented

    def __array_function__(self, func, types, args, kwargs):
        """Handle numpy arrayfunctions called on `EncodedArray` objects

        Limited functionality for now, but can be updated as needed
        """
        if func == np.bincount:
            return np.bincount(args[0].data, *args[1:], **kwargs)
        if func == np.concatenate:
            return self.__class__(func([e.data for e in args[0]]), self.encoding)
        if func == np.where:
            return self.__class__(func(args[0], args[1].data, args[2].data), encoding = self.encoding)
        if func == np.zeros_like:
            return self.__class__(func(args[0].data, *args[1:], **kwargs), encoding=self.encoding)
        if func == np.append:
            return self.__class__(func(args[0].data, args[1].data, *args[2:], **kwargs), encoding=self.encoding)
        if func == np.insert:
            return self.__class__(func(args[0].data, args[1], args[2].data, *args[3:], **kwargs), encoding = self.encoding)
        elif func in (np.lib.stride_tricks.sliding_window_view, np.lib.stride_tricks.as_strided):
            return self.__class__(func(args[0].data, *args[1:], **kwargs), self.encoding)
        
        return NotImplemented
        return super().__array_function__(func, types, args, kwargs)

    def ravel(self):
        return self.__class__(self.data.ravel(), self.encoding)

    def as_strided(self, *args, **kwargs):
        """Explicitly delegate as_strided, as it is not a arrayfunction

        This should always be used with care, and can lead to some segmentation faults!

        So don't use it :)

        """
        assert isinstance(self.data, np.ndarray) and not np.issubdtype(self.data.dtype, np.object_)
        return self.__class__(np.lib.stride_tricks.as_strided(self.data, *args, **kwargs), self.encoding)


def str_or_list_as_encoded_array(s, target_encoding):
    if isinstance(s, (EncodedArray, EncodedRaggedArray)):
        assert s.encoding == target_encoding
    elif isinstance(s, str):
        s = encode_string(s, target_encoding)
    elif isinstance(s, list):
        s = encode_list_of_strings(s, target_encoding)
    else:
        raise EncodingException("Tried encoding str or list of strings but got %s" % type(s))

    return s


def encode_string(s: str, target_encoding):
    s = EncodedArray([ord(c) for c in s], IdentityEncoding)
    s = _encode_base_encoded_array(s, target_encoding)
    return s


def encode_list_of_strings(s: str, target_encoding):
    s = EncodedRaggedArray(
        EncodedArray([ord(c) for ss in s for c in ss]),
        [len(ss) for ss in s])
    return ragged_array_as_encoded_array(s, target_encoding)


def as_encoded_array(s, target_encoding: Encoding = None) -> EncodedArray:
    """Main function used to create encoded arrays from e.g. strings orl lists.
    Can be called with already encoded arrays, and will then do nothing.

    If input is `str` or `List[str]` objects, creates an `EncodedArray` or `EncodedRaggedArray`
    object from them with the given encoding.

    If the input is an `EncodedArray` or `EncodedRaggedArray` AND input is BaseEncoded,
    encode the input to the `target_encoding` if possible. If `target_encoding` is None, nothing is done.

    Raw encoded data as `np.ndarray` objects should not be passed to this function. If you have
    already encoded data in `np.ndarray` objects, use the `EncodedArray.__init__`directly

    Parameters
    ----------
    s : str/List[str]/EnocedArray/EncodedRaggedArray
        The data to be represented in an EncodedArray
    target_encoding : Encoding
        The encoding to use in the resulting EncodedArray

    Returns
    -------
    EncodedArray
        Encoded data in an EncodedArray

    default target encoding None:
    if None: encode as base encoding if it is not encoded
    if already encoded: do nothing
    this function is not for changing encoding on stuff

    """
    if isinstance(s, (EncodedArray, EncodedRaggedArray)):
        if target_encoding is None or s.encoding == target_encoding:
            return s
        else:
            if s.encoding != BaseEncoding:
                raise EncodingException("Trying to encode already encoded array with encoding %s to encoding %s. "
                                        "This is not supported. Use the change_encoding function." % (
                    s.encoding, target_encoding))
    elif target_encoding is None:
        target_encoding = BaseEncoding

    if isinstance(s, str):
        return encode_string(s, target_encoding)
    elif isinstance(s, list):
        return encode_list_of_strings(s, target_encoding)
    elif isinstance(s, (RaggedArray, EncodedRaggedArray)):
        return ragged_array_as_encoded_array(s, target_encoding)
    elif isinstance(s, np.ndarray):
        return np_array_as_encoded_array(s, target_encoding)
    else:
        assert isinstance(s, EncodedArray)
        return _encode_encoded_array(s, target_encoding)


def _encode_encoded_array(encoded_array, target_encoding):
    """Encode an encoded array with a new encoding.
    Encoded array should either be BaseEncoded or have target_encoding"""
    assert isinstance(encoded_array, EncodedArray), (encoded_array, repr(encoded_array), type(encoded_array))
    if encoded_array.encoding == target_encoding:
        return encoded_array

    if encoded_array.encoding == BaseEncoding:
        encoded_array = _encode_base_encoded_array(encoded_array, target_encoding)
    elif target_encoding == BaseEncoding:
        encoded_array = EncodedArray(encoded_array.encoding.decode(encoded_array.data), BaseEncoding)
    else:
        raise IncompatibleEncodingsException("Can only encode EncodedArray with BaseEncoding or target encoding. "
                                             "Base encoding is %s, target encoding is %s"
                                            % (str(encoded_array.encoding), str(target_encoding)))
    return encoded_array


def _encode_base_encoded_array(encoded_array, target_encoding):
    assert encoded_array.encoding.is_base_encoding()
    encoded_array = target_encoding.encode(encoded_array.data)
    #if is_subclass_or_instance(target_encoding, NumericEncoding):
    if hasattr(target_encoding, "is_numeric"):
        encoded_array = encoded_array
    else:
        encoded_array = EncodedArray(encoded_array, target_encoding)
    return encoded_array


def np_array_as_encoded_array(s, target_encoding):
    assert is_subclass_or_instance(target_encoding, NumericEncoding), s
    return s


def ragged_array_as_encoded_array(s, target_encoding):
    data = as_encoded_array(s.ravel(), target_encoding)
    if isinstance(data, EncodedArray):
        return EncodedRaggedArray(data, s.shape)
    return RaggedArray(data, s.shape)



def from_encoded_array(encoded_array: EncodedArray) -> str:
    """Convert data in an `EncodedArray`/`EncodedRaggedArray into `str`/`List[str]`

    Unlike the `EncodedArray.__str__` this will convert all the data into strings

    Parameters
    ----------
    encoded_array : EncodedArray

    Returns
    -------
    str
        Full string representation

    Examples
    --------
    5

    """
    if isinstance(encoded_array, EncodedRaggedArray):
        return [from_encoded_array(row) for row in encoded_array]
    else:
        return "".join(chr(c) for c in encoded_array.encoding.decode(encoded_array.data))


def change_encoding(encoded_array, new_encoding):
    assert isinstance(encoded_array, (EncodedArray, EncodedRaggedArray)), \
        "Can only change encoding of EncodedArray or EncodedRaggedArray"

    new_data = new_encoding.encode(
        encoded_array.encoding.decode(encoded_array.ravel())
    )

    if isinstance(encoded_array, EncodedArray):
        return EncodedArray(new_data, new_encoding)
    elif isinstance(encoded_array, EncodedRaggedArray):
        return EncodedRaggedArray(EncodedArray(new_data, new_encoding), encoded_array.shape)
